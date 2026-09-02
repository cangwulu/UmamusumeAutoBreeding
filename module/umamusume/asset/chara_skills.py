# -*- coding: utf-8 -*-
"""马娘自带技能查询（「马娘 → 自带技能」映射，运行时**不联网**）。

数据来源：
    resource/umamusume/data/chara_skills.json
    （tools/build_chara_skills.py 从 pretty-derby 上游 db.json 构建，
      130 个角色：固有技能 130/130、觉醒技能 130/130 全覆盖，
      另按形态（卡）区分初始技能）

为什么不用 BWIKI：BWIKI 技能速查表**不含「所属马娘」字段**
（其键 17 是技能图标 ID，见 Skill_Quick.js 的 fileName()），
所以马娘 → 技能归属只能来自 pretty-derby 的 db.json。

技能分三类（对育成决策的意义不同）：
    * unique_skills     固有技能：角色级，全场唯一 1 个，天生自带
    * awakening_skills  觉醒技能：角色级，随觉醒等级解锁（约 4 个）
    * initial_skills    初始技能：**形态级**，同一角色的不同卡（形态）不同

主要用途（育成流程里最实在的一条）：
    **避免重复学习马娘已经自带的技能**——白花技能点。
    用 owned_skill_names() 取自带技能名集合，或用 is_owned() 判定。
    注意「自带的」不等于「已学到的」：觉醒技能要觉醒等级到了才有，
    所以 is_owned() 有 include_awakening 开关（默认 True，保守不学）。

用法：
    from module.umamusume.asset.chara_skills import get_chara_skills, is_owned
    get_chara_skills("特别周")          # -> 角色完整记录 dict 或 None
    owned_skill_names("特别周")          # -> {"流星", "道恶○", ...}
    is_owned("特别周", "道恶○")          # -> True

CLI：
    python module/umamusume/asset/chara_skills.py 特别周
    python module/umamusume/asset/chara_skills.py 特别周 --card 特别梦想家
    python module/umamusume/asset/chara_skills.py --list
"""

import json
import os
import sys
import threading

# 允许「直接跑脚本」而不只是被 import：把项目根塞进 sys.path。
# chara_skills.py 位于 <项目根>/module/umamusume/asset/ 下，往上 4 层即项目根。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from bot.recog.fuzzy_match import FuzzyIndex, cosine_sim
from module.umamusume.name_resolver import get_resolver

CHARA_SKILLS_PATH = "resource/umamusume/data/chara_skills.json"

# 角色名检索下限 / 接受线。角色名（3~5 字中文）比技能名更固定，但 OCR 仍可能出错，
# 沿用 skill_order 的双阈值策略：宽召回 + 真实 cosine 复核。
# 注意：FuzzyIndex.query() 单命中时返回的是**递减阈值**而非真实相似度，
# 接受判定必须用 cosine_sim() 重算。
_SEARCH_FLOOR = 0.30
_ACCEPT = 0.50


class CharaSkillDB(object):
    """马娘技能库的懒加载单例。"""

    def __init__(self, path=CHARA_SKILLS_PATH):
        self.path = path
        self.characters = []
        self._by_name = {}       # 中文角色名 -> 角色记录
        self._by_jp_name = {}    # 日文角色名 -> 角色记录
        self._by_card_name = {}  # 卡（形态）名 -> (角色记录, 卡记录)
        self._by_chara_jp = {}   # 日文角色规范键 -> 角色记录
        self._by_card_jp = {}    # 日文形态规范键 -> (角色记录, 卡记录)
        self._index = None       # FuzzyIndex(中文角色名 + 卡名)

    def load(self):
        if not os.path.isfile(self.path):
            raise FileNotFoundError(
                "马娘技能库不存在：%s\n请先运行：python tools/build_chara_skills.py"
                "（依赖 tools/.cache/db.json）" % self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.characters = data.get("characters", [])
        self._by_name = {}
        self._by_card_name = {}
        self._by_chara_jp = {}
        self._by_card_jp = {}
        for c in self.characters:
            nm = c.get("name") or ""
            if nm:
                self._by_name[nm] = c
            jp = c.get("name_jp") or ""
            if jp:
                self._by_jp_name[jp] = c
                self._by_chara_jp[jp] = c
            for card in c.get("cards", []):
                cn = card.get("card_name") or ""
                if cn:
                    self._by_card_name[cn] = (c, card)
                cjp = card.get("card_jp") or ""
                if cjp:
                    self._by_card_jp[cjp] = (c, card)
        # 角色名与卡名一起建索引，便于直接查形态
        keys = list(self._by_name.keys()) + list(self._by_card_name.keys())
        self._index = FuzzyIndex(keys)
        return self

    @property
    def index(self):
        if self._index is None:
            self.load()
        return self._index

    def match(self, name):
        """角色名 / 卡名模糊匹配。

        优先走统一名称解析层 name_resolver（任何表面名 -> 日文规范键），
        再按规范键在本库索引里精确定位（角色级 / 形态级），从而让
        BWIKI 中文形态名与 pretty-derby 中文形态名都能命中同一张卡。
        解析层未命中才退回原有的精确 + 模糊匹配。
        :return: (chara_record, matched_name, score, card_record_or_None)
                 未命中返回 (None, None, 0.0, None)
        """
        if not self.characters:
            self.load()
        if not name:
            return None, None, 0.0, None
        # 0) 统一名称解析层
        try:
            r = get_resolver()
            jp_key, score = r.canonical(name)
            if jp_key:
                kind = r.kind(jp_key)
                if kind == "chara":
                    rec = self._by_chara_jp.get(jp_key)
                    if rec is not None:
                        return rec, rec.get("name", name), max(score, 0.9), None
                elif kind == "form":
                    pair = self._by_card_jp.get(jp_key)
                    if pair is not None:
                        return pair[0], name, max(score, 0.9), pair[1]
        except Exception:
            pass
        # 1) 精确：中文角色名
        rec = self._by_name.get(name)
        if rec is not None:
            return rec, name, 1.0, None
        # 2) 精确：日文角色名
        rec = self._by_jp_name.get(name)
        if rec is not None:
            return rec, rec.get("name", name), 1.0, None
        # 3) 精确：卡（形态）名
        pair = self._by_card_name.get(name)
        if pair is not None:
            return pair[0], name, 1.0, pair[1]
        # 4) 模糊：角色名 + 卡名混合索引
        res = self.index.query([name], min_threshold=_SEARCH_FLOOR)
        if not res or not res[0]:
            return None, None, 0.0, None
        entry = res[0]
        real = cosine_sim(name, entry)
        if real < _ACCEPT:
            return None, None, 0.0, None
        if entry in self._by_name:
            return self._by_name[entry], entry, real, None
        pair = self._by_card_name.get(entry)
        if pair is not None:
            return pair[0], entry, real, pair[1]
        return None, None, 0.0, None


_DB = None
_LOCK = threading.Lock()


def get_db(reload=False):
    """取得马娘技能库单例。"""
    global _DB
    if _DB is not None and not reload:
        return _DB
    with _LOCK:
        if _DB is None or reload:
            _DB = CharaSkillDB().load()
    return _DB


def search(name, topn=5, min_score=0.30):
    """相似角色候选列表（用于 match() 未命中时的兜底 / 人工确认）。

    马娘只有 130 个角色，直接暴力算 cosine 即可，不必走索引。
    刻意不用 FuzzyIndex，因为它在单命中时返回的是递减阈值而非真实相似度，
    排序不可靠。

    :return: list[dict]，每项 {name, score, chara, card}，按相似度降序
             name 为角色名或卡名，chara 恒为该角色记录，card 为形态记录或 None
    """
    db = get_db()
    if not name:
        return []
    scored = []
    for c in db.characters:
        nm = c.get("name") or ""
        if nm:
            scored.append((cosine_sim(name, nm), nm, c, None))
        for card in c.get("cards") or []:
            cn = card.get("card_name") or ""
            if cn:
                scored.append((cosine_sim(name, cn), cn, c, card))
    scored.sort(key=lambda x: -x[0])
    return [{"name": nm, "score": round(s, 3), "chara": c, "card": cd}
            for s, nm, c, cd in scored[:topn] if s >= min_score]


def list_characters():
    """所有马娘中文名（按库内顺序）。"""
    return [c.get("name", "") for c in get_db().characters if c.get("name")]


def get_chara_skills(name):
    """按角色名 / 卡名查完整记录。

    :param name: 中文角色名、日文角色名或卡（形态）名
    :return: dict(name, name_jp, unique_skills, awakening_skills, cards) 或 None
    """
    rec, _matched, _sc, _card = get_db().match(name)
    return rec


def unique_skill_of(name):
    """该马娘的固有技能（dict 或 None）。"""
    rec = get_chara_skills(name)
    if not rec:
        return None
    lst = rec.get("unique_skills") or []
    return lst[0] if lst else None


def awakening_skills_of(name):
    """该马娘的觉醒技能列表（角色级）。"""
    rec = get_chara_skills(name)
    return (rec or {}).get("awakening_skills") or []


def initial_skills_of(name, card=None):
    """该马娘的初始技能（形态级）。

    :param card: 指定卡（形态）名；None 时取全部形态的并集
    :return: 技能 dict 列表
    """
    rec, _m, _s, card_rec = get_db().match(name)
    if not rec:
        return []
    cards = rec.get("cards") or []
    if card:
        cards = [c for c in cards if c.get("card_name") == card]
    elif card_rec is not None:
        # 传进来的就是卡名，锁定该形态
        cards = [card_rec]
    out = []
    for c in cards:
        for s in c.get("initial_skills") or []:
            out.append(s)
    return out


def owned_skill_names(name, card=None, include_awakening=True):
    """该马娘「自带」的技能名集合（用于避免重复学习）。

    :param card: 指定形态；None 时含全部形态
    :param include_awakening: 是否把觉醒技能算作已拥有。
        默认 True（保守：不花技能点学将来会白送的技能）。
        若你的策略是「觉醒等级还早，该学就学」，传 False。
    :return: set[str]（中 / 日文技能名都收录，便于对 OCR 结果做匹配）
    """
    rec, _m, _s, card_rec = get_db().match(name)
    if not rec:
        return set()
    if card is None and card_rec is not None:
        card = card_rec.get("card_name")
    names = set()
    for s in rec.get("unique_skills") or []:
        _add_names(names, s)
    if include_awakening:
        for s in rec.get("awakening_skills") or []:
            _add_names(names, s)
    for s in initial_skills_of(name, card):
        _add_names(names, s)
    return names


def _add_names(bucket, skill):
    for key in ("name", "name_jp"):
        v = skill.get(key)
        if v:
            bucket.add(v)


def is_owned(name, skill_name, card=None, include_awakening=True):
    """该马娘是否已自带某技能（精确名匹配）。

    OCR 出的技能名可能带错字，建议先用 skill_order.match() 归一化为
    库内规范名再调用本函数。
    """
    if not skill_name:
        return False
    return skill_name in owned_skill_names(
        name, card=card, include_awakening=include_awakening)


def rank_owned(name, card=None, include_awakening=True, topn=None):
    """自带技能按 grade_value（评价分）从高到低排序。

    可用于「优选策略」：看这只马娘白送的技能里哪些最值钱。
    :return: 有序 list[dict]，每项含 name / grade_value / kind / describe
    """
    rec, _m, _s, card_rec = get_db().match(name)
    if not rec:
        return []
    if card is None and card_rec is not None:
        card = card_rec.get("card_name")
    out = []
    for kind, key in (("固有", "unique_skills"), ("觉醒", "awakening_skills")):
        if kind == "觉醒" and not include_awakening:
            continue
        for s in rec.get(key) or []:
            out.append(_brief(s, kind))
    for s in initial_skills_of(name, card):
        out.append(_brief(s, "初始"))
    out.sort(key=lambda x: x["grade_value"] or 0, reverse=True)
    return out[:topn] if topn else out


def _brief(skill, kind):
    return {
        "name": skill.get("name", ""),
        "name_jp": skill.get("name_jp", ""),
        "grade_value": skill.get("grade_value"),
        "need_skill_point": skill.get("need_skill_point"),
        "rare": skill.get("rare", ""),
        "kind": kind,
        "describe": skill.get("describe", ""),
    }


def suggest_not_to_learn(name, candidates, card=None, include_awakening=True):
    """从一组「候选可学技能」里剔除马娘已自带的（避免白花技能点）。

    :param candidates: 技能名列表（可含错字，走精确集合比对）
    :return: (建议去学的, 建议跳过的) 两个列表
    """
    owned = owned_skill_names(name, card=card,
                              include_awakening=include_awakening)
    keep, skip = [], []
    for nm in candidates:
        (skip if nm in owned else keep).append(nm)
    return keep, skip


if __name__ == "__main__":
    import argparse
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="查询马娘自带技能（固有 / 觉醒 / 各形态初始技能）")
    ap.add_argument("name", nargs="?", help="马娘中文名 / 日文名 / 卡（形态）名")
    ap.add_argument("--card", help="只看指定形态（卡名）")
    ap.add_argument("--no-awakening", action="store_true",
                    help="把觉醒技能不算作「已拥有」")
    ap.add_argument("--list", action="store_true", help="列出全部马娘名")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    if args.list or not args.name:
        if args.json:
            print(json.dumps(list_characters(), ensure_ascii=False))
        else:
            names = list_characters()
            print("共 %d 个马娘：" % len(names))
            for i in range(0, len(names), 8):
                print("  " + "  ".join(names[i:i + 8]))
        sys.exit(0)

    rec = get_chara_skills(args.name)
    if rec is None:
        print("未找到马娘：%s" % args.name)
        cands = search(args.name)
        if cands:
            print("你是否想找（自动匹配未达接受线，仅作提示）：")
            for cd in cands:
                kind = "形态" if cd["card"] is not None else "角色"
                print("  [%-2s] %-22s 相似度 %.2f" % (
                    kind, cd["name"], cd["score"]))
        else:
            print("提示：可用 --list 查看全部马娘名")
        sys.exit(1)

    if args.json:
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        sys.exit(0)

    inc_awake = not args.no_awakening
    print("=" * 56)
    print("%s  （%s）" % (rec.get("name", ""), rec.get("name_jp", "")))
    print("=" * 56)
    for s in rec.get("unique_skills") or []:
        print("  [固有] %-24s %s分  %s" % (
            s.get("name", ""), s.get("grade_value"), s.get("describe", "")[:40]))
    if args.card is None:
        for s in rec.get("awakening_skills") or []:
            print("  [觉醒] %-24s %s分  %s" % (
                s.get("name", ""), s.get("grade_value"), s.get("describe", "")[:40]))
        for c in rec.get("cards") or []:
            nm = c.get("card_name", "")
            ini = [x.get("name", "") for x in c.get("initial_skills") or []]
            print("  [初始] %-24s %s" % (nm, " / ".join(ini)))
    else:
        hit = [c for c in rec.get("cards") or [] if c.get("card_name") == args.card]
        if not hit:
            print("  未找到形态：%s（可用形态：%s）" % (
                args.card, " / ".join(c.get("card_name", "")
                                      for c in rec.get("cards") or [])))
        for c in hit:
            print("  [初始] %-24s %s" % (
                c.get("card_name", ""),
                " / ".join(x.get("name", "") for x in c.get("initial_skills") or [])))
    print("-" * 56)
    print("自带技能名集合（用于去重，含觉醒=%s）：" % inc_awake)
    owned = sorted(owned_skill_names(args.name, card=args.card,
                                     include_awakening=inc_awake))
    print("  " + " / ".join(owned))
