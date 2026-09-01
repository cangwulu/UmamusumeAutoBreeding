# -*- coding: utf-8 -*-
"""相性（固定相性分）查询与继承打分（运行时**不联网**）。

数据来源：
    resource/umamusume/data/affinity.json
    （tools/build_affinity.py 从 BWIKI「简中相性计算器」页面构建，
      84 个角色 / 792 个关系组，数据版本见 meta.data_version）

计算规则（来源：BWIKI「相性计算器计算方法」页）：
    * 每个角色属于多个「关系组」（学年/宿舍/寝室/同期/家人/对手…），
      每个组有自己的固定分 point。
    * 两角色的固定相性分 = 两者**共同所在**关系组的 point 之和。
    * 三角色的固定相性分 = 三者共同所在关系组的 point 之和。
    * 继承树（0=目标马, 1/2=父母, 3~6=祖父母）各号单独打分：
          1号 = 组(0,1)
          2号 = 组(0,2) + 组(1,2)
          3号 = 组(0,1,3)；4号 = 组(0,1,4)；5号 = 组(0,2,5)；6号 = 组(0,2,6)
          祖父母与目标马同角色时该号记 0 分
    * 等级：△ ≥0 / 〇 ≥51 / ⌾ ≥151（对固定分；胜鞍另算）
    * ⚠ 本模块**不含胜鞍加成**：同一分支上每有一场相同比赛的夺冠履历
      （G1 胜鞍重合，OP/Pre-OP/新马战/URA 不计）额外 +1pt，
      需要用赛程数据另行计算后叠加（见 docs/strategy_integrated.md C.4）。

用法：
    from module.umamusume.asset.affinity import AffinityDB
    db = AffinityDB.get()
    db.pair_score("小栗帽", "玉藻十字")            # -> int（寝室+2 等）
    db.inherit_scores("小栗帽", "特别周", "无声铃鹿",
                      "东海帝王", None, None, None)  # -> {'s1':..,'s2':..,...,'total':..}
    db.grade(152)                                  # -> '⌾'

CLI：
    python module/umamusume/asset/affinity.py 小栗帽 玉藻十字
    python module/umamusume/asset/affinity.py --tree 小栗帽 特别周 无声铃鹿 东海帝王
    python module/umamusume/asset/affinity.py --best 小栗帽 特别周   # 帮父母2选角
"""

import json
import os
import sys
import threading

# 允许「直接跑脚本」而不只是被 import：把项目根塞进 sys.path。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from bot.recog.fuzzy_match import cosine_sim

AFFINITY_PATH = "resource/umamusume/data/affinity.json"

# 角色名（3~5 字中文）OCR 容错：宽召回 + 真实 cosine 复核。
# 注意：search() 类接口不要走 FuzzyIndex（单命中返回递减阈值，排序不可靠），
# 直接对全量名字暴力算 cosine_sim 排序。
_ACCEPT = 0.50


class AffinityDB(object):
    """相性库的懒加载单例。"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, path=AFFINITY_PATH):
        self.path = path
        self.meta = {}
        self.characters = {}   # id -> 中文名
        self.groups = []       # [{'type','point','category','detail','members'}]
        self._by_name = {}     # 中文名 -> id
        self._sets = []        # [(frozenset(member_ids), point)]，只留 2+ 人组

    # ------------------------------------------------------------------ 加载

    @classmethod
    def get(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = cls()
                    inst.load()
                    cls._instance = inst
        return cls._instance

    def load(self):
        if not os.path.isfile(self.path):
            raise FileNotFoundError(
                "相性库不存在：%s\n请先运行：python tools/build_affinity.py"
                "（依赖 tools/.cache/affinity_*.json）" % self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.meta = data.get("meta", {})
        self.characters = {int(k): v for k, v in data.get("characters", {}).items()}
        self._by_name = {v: k for k, v in self.characters.items()}
        self.groups = data.get("groups", [])
        self._sets = [(frozenset(g["members"]), g["point"])
                      for g in self.groups if len(g["members"]) >= 2]

    # --------------------------------------------------------------- 名字解析

    def resolve(self, name_or_id):
        """角色名（容错）或数字 id -> 内部 id；解析失败返回 None。"""
        if isinstance(name_or_id, int):
            return name_or_id if name_or_id in self.characters else None
        if name_or_id is None:
            return None
        s = str(name_or_id)
        if s in self._by_name:                      # 精确命中
            return self._by_name[s]
        if s.isdigit():                             # 数字字符串当 id
            i = int(s)
            return i if i in self.characters else None
        best, best_sim = None, 0.0                  # 模糊：全量暴力 cosine
        for name, cid in self._by_name.items():
            sim = cosine_sim(s, name)
            if sim > best_sim:
                best, best_sim = cid, sim
        return best if best_sim >= _ACCEPT else None

    def name(self, cid):
        return self.characters.get(cid, str(cid))

    def search(self, name, limit=5):
        """候选角色列表（真实 cosine 降序），供确认，不自动接受。"""
        scored = sorted(
            ((cosine_sim(str(name), n), n) for n in self._by_name),
            key=lambda x: -x[0])
        return [{"name": n, "sim": round(s, 3)} for s, n in scored[:limit] if s > 0]

    # ------------------------------------------------------------------- 打分

    def pair_score(self, a, b):
        """两角色固定相性分 = 共同所在关系组 point 之和。"""
        ia, ib = self.resolve(a), self.resolve(b)
        if ia is None or ib is None:
            return 0
        return sum(p for members, p in self._sets
                   if ia in members and ib in members)

    def triple_score(self, a, b, c):
        """三角色固定相性分 = 三者共同所在关系组 point 之和。"""
        ids = {self.resolve(x) for x in (a, b, c)}
        if None in ids or len(ids) < 3:
            return 0
        return sum(p for members, p in self._sets if ids <= members)

    def inherit_scores(self, target, parent1, parent2,
                       gp1=None, gp2=None, gp3=None, gp4=None):
        """按「相性计算器计算方法」页的继承树打分。

        参数均可传中文名 / id / None（祖父母可缺省）。
        返回 {'s1'..'s6', 'total'}；祖父母与目标马同角色时该号记 0。
        ⚠ 只含固定相性分，不含胜鞍加成。
        """
        t = self.resolve(target)
        if t is None:
            return {'s1': 0, 's2': 0, 's3': 0, 's4': 0, 's5': 0, 's6': 0, 'total': 0}
        p1, p2 = self.resolve(parent1), self.resolve(parent2)

        def _pair(x, y):
            if x is None or y is None:
                return 0
            return sum(p for members, p in self._sets if x in members and y in members)

        def _triple(x, y, z):
            if x is None or y is None or z is None:
                return 0
            s = {x, y, z}
            return sum(p for members, p in self._sets if s <= members)

        def _gp(z):
            """祖父母号：与目标马同角色记 0 分（页面规则）。"""
            zid = self.resolve(z) if z is not None else None
            if zid is None:
                return 0
            return 0 if zid == t else zid

        g1, g2, g3, g4 = _gp(gp1), _gp(gp2), _gp(gp3), _gp(gp4)
        # 与目标马同角色的祖父母，所有涉及它的组都按 0 处理（传 None 即可）
        s1 = _pair(t, p1)
        s2 = _pair(t, p2) + _pair(p1, p2)
        s3 = _triple(t, p1, g1) if g1 is not None else 0
        s4 = _triple(t, p1, g2) if g2 is not None else 0
        s5 = _triple(t, p2, g3) if g3 is not None else 0
        s6 = _triple(t, p2, g4) if g4 is not None else 0
        return {'s1': s1, 's2': s2, 's3': s3, 's4': s4, 's5': s5, 's6': s6,
                'total': s1 + s2 + s3 + s4 + s5 + s6}

    @staticmethod
    def grade(score):
        """固定分 -> 游戏内相性等级（△ / 〇 / ⌾）。"""
        if score >= 151:
            return '⌾'
        if score >= 51:
            return '〇'
        return '△'

    # ------------------------------------------------------------------ 检索

    def shared_groups(self, *names):
        """列出几个角色共同所在的关系组（调试 / 解释用）。"""
        ids = {self.resolve(x) for x in names}
        ids.discard(None)
        out = []
        for g in self.groups:
            if ids <= set(g["members"]):
                out.append({'category': g['category'], 'detail': g['detail'],
                            'point': g['point']})
        return out

    def best_partners(self, name, exclude=(), limit=10):
        """给定目标马，全库找固定相性分最高的搭档（按两人分排序）。

        exclude：要排除的角色（比如已经选定的父母另一方）。
        """
        cid = self.resolve(name)
        if cid is None:
            return []
        skip = {self.resolve(x) for x in exclude} | {cid}
        skip.discard(None)
        scores = {}
        for members, p in self._sets:
            if cid in members:
                for m in members:
                    if m not in skip:
                        scores[m] = scores.get(m, 0) + p
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:limit]
        return [{'name': self.name(m), 'score': s} for m, s in ranked]


# ----------------------------------------------------------------------- CLI

def _main(argv):
    db = AffinityDB.get()
    if not argv:
        print("用法：affinity.py <角色A> <角色B> [--tree 目标马 父母1 父母2 (祖父母×4)]"
              " [--best 角色 (排除…)] [--search 名字片段]")
        return 1
    if argv[0] == '--search':
        for hit in db.search(argv[1] if len(argv) > 1 else ''):
            print('%s  %.3f' % (hit['name'], hit['sim']))
        return 0
    if argv[0] == '--best':
        name = argv[1]
        exclude = argv[2:]
        for hit in db.best_partners(name, exclude=exclude):
            print('%-8s %3d  %s' % (hit['name'], hit['score'],
                                    db.grade(hit['score'])))
        return 0
    if argv[0] == '--tree':
        names = argv[1:]
        kw = dict(zip(['target', 'parent1', 'parent2', 'gp1', 'gp2', 'gp3', 'gp4'],
                      names + [None] * (7 - len(names))))
        for k, v in kw.items():
            if v is None:
                continue
            r = db.resolve(v)
            print('%-7s %-8s -> %s' % (k, v, db.name(r) if r is not None else '(未解析!)'))
        sc = db.inherit_scores(**kw)
        for k in ('s1', 's2', 's3', 's4', 's5', 's6'):
            print('%s = %d' % (k, sc[k]))
        print('total = %d  grade = %s' % (sc['total'], db.grade(sc['total'])))
        return 0
    a, b = argv[0], argv[1]
    s = db.pair_score(a, b)
    print('%s × %s 固定相性分 = %d (%s)' % (a, b, s, db.grade(s)))
    for g in db.shared_groups(a, b):
        print('  [%s] %s +%d' % (g['category'], g['detail'], g['point']))
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
