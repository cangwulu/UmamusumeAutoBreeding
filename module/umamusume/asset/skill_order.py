# -*- coding: utf-8 -*-
"""技能排序引擎（「技能排序」核心，运行时**不联网**）。

数据来源（双源，优先级从高到低）：
1. resource/umamusume/data/skill_bwiki.json —— **国服 BWIKI 简中技能表**
   （tools/fetch_bwiki_skills.py 抓取，1000 条简中技能名 + 社区评价分 100% 覆盖，
   与国服 OCR 出的简中名直接对齐，**主排序依据**）。
2. resource/umamusume/data/skill_db.json —— pretty-derby 上游库
   （日/繁中名，评分来自 2023 快照覆盖率有限，作为 BWIKI 未命中时的兜底）。

设计目标：
    bot 在育成中 OCR 识别出一组「可学技能名」（可能带错字、有前缀/后缀变体），
    本模块把它们模糊匹配到技能库，按「综合分」从高到低排序，输出一个有序列表。
    这个有序列表就是「技能排序」的结果，供 script_cultivate_learn_skill 的
    贪心选取逻辑消费；而「具体选哪几个、配合什么养成策略」属于「优选策略」，
    按计划暂留空，由后续策略模块使用本排序结果。

综合分（越高越优先）：
    * BWIKI 命中：直接用其「评价分」（含减益红技负分，天然排到最后）；
    * 仅 pretty-derby 命中：score 或 稀有度*1000+数值 兜底；
    * 双源都未命中：-1.0（排在减益技能之前、正常技能之后）。

用法：
    from module.umamusume.asset.skill_order import rank_skills
    ranked = rank_skills(["力量之歌", "错字技能名", "金剑"])   # -> 有序 dict 列表
"""

import json
import os
import threading

from bot.recog.fuzzy_match import FuzzyIndex, cosine_sim

SKILL_DB_PATH = "resource/umamusume/data/skill_db.json"
SKILL_BWIKI_PATH = "resource/umamusume/data/skill_bwiki.json"

# 稀有度 -> 权重（仅用于无 score 时的兜底排序；越高越优先）
_RARITY_WEIGHT = {
    5: 5000,   # 固有 / SSR
    4: 4000,   # SR
    3: 3000,   # R
    2: 2000,
    1: 1000,
}
# 文字稀有度字段（rare）兜底映射
_RARE_TEXT_WEIGHT = {
    "固有": 5000,
    "SSR": 5000,
    "SR": 4000,
    "R": 3000,
    "N": 1000,
}
# BWIKI 简中稀有度兜底（BWIKI 全部带评价分，此映射仅防御性使用）
_RARE_BWIKI_WEIGHT = {
    "独特": 5000,   # 固有/独特技能
    "传说": 4000,   # 金技能
    "进化": 3500,   # 进化技能
    "剧情": 3000,
    "普通": 1000,   # 白技能
}


def _composite(rec):
    """单条技能记录的「综合分」。"""
    sc = rec.get("score")
    if isinstance(sc, (int, float)):
        return float(sc)
    rarity = rec.get("rarity")
    if isinstance(rarity, str):  # BWIKI 中文稀有度
        w = _RARE_BWIKI_WEIGHT.get(rarity, 1000)
        return float(w)
    w = _RARITY_WEIGHT.get(rarity) if isinstance(rarity, int) else None
    if w is None:
        rare = rec.get("rare") or ""
        w = _RARE_TEXT_WEIGHT.get(rare, 1000)
    av = rec.get("ability_value")
    if not isinstance(av, (int, float)):
        av = 0
    return float(w + av)


class SkillDB(object):
    """技能库的懒加载单例：BWIKI 简中主库 + pretty-derby 兜底库。"""

    def __init__(self, path=SKILL_DB_PATH, bwiki_path=SKILL_BWIKI_PATH):
        self.path = path
        self.bwiki_path = bwiki_path
        self.skills = []            # pretty-derby 记录
        self.bwiki_skills = []      # BWIKI 简中记录
        self._by_name = {}          # pretty-derby 规范名 -> record
        self._by_bwiki_name = {}    # BWIKI 简中名 -> record
        self._name_index = None     # FuzzyIndex(pretty-derby 名)
        self._bwiki_index = None    # FuzzyIndex(BWIKI 简中名)

    def load(self):
        # 主库：BWIKI 简中（文件缺失时降级，不致命）
        if os.path.isfile(self.bwiki_path):
            with open(self.bwiki_path, encoding="utf-8") as f:
                bdata = json.load(f)
            self.bwiki_skills = bdata.get("skills", [])
            self._by_bwiki_name = {
                s.get("name", ""): s for s in self.bwiki_skills if s.get("name")}
            self._bwiki_index = FuzzyIndex(list(self._by_bwiki_name.keys()))
        # 兜底库：pretty-derby
        if not os.path.isfile(self.path):
            raise FileNotFoundError(
                "技能库不存在：%s\n请先运行：python tools/build_event_db.py" % self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.skills = data.get("skills", [])
        self._by_name = {s.get("name", ""): s for s in self.skills if s.get("name")}
        self._name_index = FuzzyIndex(list(self._by_name.keys()))
        return self

    @property
    def name_index(self):
        if self._name_index is None:
            self.load()
        return self._name_index

    # BWIKI 简中技能名普遍很短（<=5 字占 63%），2-gram cosine 对短串天然偏低，
    # 故检索下限放宽到 0.30 召回候选，再用「真实 cosine」>= 0.50 做接受线。
    # 实测（300 随机名错 1 字）：正确命中 36%、有害误配 0、垃圾名 0 误配；
    # 未命中的（多为 <=4 字短名错字）回落 -1 中性排序，不会错学技能。
    _BWIKI_SEARCH_FLOOR = 0.30
    _BWIKI_ACCEPT = 0.50
    _DERBY_ACCEPT = 0.6   # derby 名较长（日/繁中），保持原阈值

    def match(self, name, min_score=None):
        """把 OCR 出的技能名模糊匹配到库里一条技能。

        先查 BWIKI 简中主库（国服 OCR 名直接对齐），未命中再查 pretty-derby。
        注意：BWIKI 接受判定用**真实 cosine 相似度**（而非 query 返回的阈值分），
        因为 query 在单命中时返回的是递减阈值而非实际相似度。
        :param min_score: BWIKI 真实 cosine 接受线（None 用默认 0.50；derby 固定 0.6）
        返回 (record, score, source) 或 (None, 0, None)，source ∈ {"bwiki", "derby"}。
        """
        if not self.skills and not self.bwiki_skills:
            self.load()
        if not name:
            return None, 0.0, None
        accept = self._BWIKI_ACCEPT if min_score is None else min_score
        # 1) BWIKI 简中主库
        if self._bwiki_index is not None:
            entry, _ = self._bwiki_index.query([name], min_threshold=self._BWIKI_SEARCH_FLOOR)
            if entry:
                real = cosine_sim(name, entry)
                if real >= accept:
                    rec = self._by_bwiki_name.get(entry)
                    if rec is not None:
                        return rec, real, "bwiki"
        # 2) pretty-derby 兜底
        res = self.name_index.query([name])
        if res and res[0] and res[1] >= self._DERBY_ACCEPT:
            rec = self._by_name.get(res[0])
            return rec, res[1], "derby"
        return None, 0.0, None


_DB = None
_LOCK = threading.Lock()


def get_skill_db(path=SKILL_DB_PATH, reload=False):
    global _DB
    if _DB is not None and not reload:
        return _DB
    with _LOCK:
        if _DB is None or reload:
            _DB = SkillDB(path).load()
    return _DB


def composite_of(name, min_match=None):
    """单条技能名的综合分（未匹配返回 -1.0）。供 cultivate 流程做同级细分排序。"""
    rec, _, _ = get_skill_db().match(name, min_match)
    if rec is None:
        return -1.0
    return _composite(rec)


def rank_skills(names, topn=None, min_match=None):
    """对一组 OCR 出的技能名排序。

    :param names: 技能名列表（可能带错字 / 变体）
    :param topn:  只返回前 N 个（None=全部）
    :param min_match: 模糊匹配最低相似度
    :return: 有序 list[dict]，每项含
             name(原始输入), matched(库内规范名或None), score(匹配度),
             composite(综合分), rarity, ability_value, describe, source
    """
    db = get_skill_db()
    out = []
    for nm in names:
        rec, sc, src = db.match(nm, min_match)
        if rec is not None:
            comp = _composite(rec)
            rarity = rec.get("rarity")
            av = rec.get("ability_value")
            describe = rec.get("describe") or rec.get("desc", "")
        else:
            comp = -1.0          # 未匹配：排到最后（减益负分技能之下除外）
            rarity = None
            av = None
            describe = ""
        out.append({
            "name": nm,
            "matched": rec.get("name") if rec else None,
            "score": round(sc, 3),
            "composite": comp,
            "rarity": rarity,
            "ability_value": av,
            "describe": describe,
            "source": src,
        })
    out.sort(key=lambda x: (x["composite"], x["score"]), reverse=True)
    if topn:
        out = out[:topn]
    return out


def rank_learnable(skill_dicts, name_key="skill_name", topn=None, min_match=None):
    """同上，但输入是 get_skill_list 返回的技能 dict 列表，按 composite 排序后
    只回传排序后的原 dict（便于直接替换优先级）。"""
    ranked = rank_skills([s.get(name_key, "") for s in skill_dicts],
                         topn=None, min_match=min_match)
    by_name = {r["name"]: r for r in ranked}
    return sorted(
        skill_dicts,
        key=lambda s: by_name.get(s.get(name_key, ""), {}).get("composite", -1.0),
        reverse=True,
    )


if __name__ == "__main__":
    import sys
    sample = ["力量之歌", "速度之星", "金剑", "NotExistSkillXYZ"]
    if len(sys.argv) > 1:
        sample = sys.argv[1:]
    for r in rank_skills(sample):
        print("%-12s matched=%-12s comp=%.1f r=%s" % (
            r["name"], str(r["matched"]), r["composite"], r["rarity"]))
