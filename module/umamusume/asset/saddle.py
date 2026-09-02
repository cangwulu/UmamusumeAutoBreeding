# -*- coding: utf-8 -*-
"""胜鞍（Saddle/相性加成）—— 2023-02-24 平衡调整后的现行规则。

规则来源（巴哈《因子丨歷戰種馬丨相性》2/24 改版 + umalator SuccessionPlanner 实现）：
  * 仅 **G1** 比赛的夺冠履历参与胜鞍加分（G2/G3/OP 不再计）。
  * 同一场 G1 只计一次（同一比赛多场次按 race id 去重）。
  * 继承树 7 个相性项里，凡「两匹种马都赢过的 G1」重合即加分，
    单场 +G1_COMPATIBILITY_POINTS（=3，与 umalator 一致）。
  * **父辈之间（B,C）也计**（改版新增）。
  * **无金章/称号加成**（经典三冠等不再额外计分，旧版规则已废弃）。
  * 同名但异场的史实还原赛不计同一胜鞍 —— 国服 race_bwiki 中 G1 名唯一
    （同名异场=0），故用 race id 即可；若未来出现同名异场，用 (名,场地) 复合键。

用法：
    from module.umamusume.asset.saddle import saddle_points, g1_ids_from_route
    a = g1_ids_from_route(route_a)   # route = route_planner.generate_route 输出
    b = g1_ids_from_route(route_b)
    saddle_points(a, b)              # -> (重合场数, 加分)

    # 全相性（固定分 + 胜鞍）示例见 stud_planner 的历战代输出。
"""
from typing import Collection, Iterable, List, Optional, Tuple

# 单场重合 G1 的胜鞍分（uma-tools SuccessionPlanner: G1_COMPATIBILITY_POINTS=3）
G1_COMPATIBILITY_POINTS = 3
# 两匹不同「历战路线」的种马，在草地英里中距离的大致公共 G1 数
# （umalator DIFFERENT_ROUTE_COMMON_G1=16）—— 本模块不内置路线表，
# 实际重合按双方真实 G1 覆盖集合并集计算，无需此近似。
# 保留常量便于将来做「未指定赛程时的默认估算法」。
DIFFERENT_ROUTE_COMMON_G1 = 16


def g1_ids_from_route(route: Iterable[dict]) -> List[int]:
    """从 route_planner.generate_route 的输出中抽出去重后的 G1 比赛 id 集合。

    route 每项形如 {'race': {...}, ...}，race 含 id/grade。
    兼容 route_stats 输出的 {'g1_list': [名字...]}（此时返回空，调用方需换接口）。
    """
    seen: set = set()
    out: List[int] = []
    for step in route:
        race = step.get("race") or {}
        if race.get("grade") != "G1":
            continue
        rid = race.get("id")
        if rid is None:
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(int(rid))
    return out


def g1_ids_from_names(names: Collection[str],
                      race_db=None) -> List[int]:
    """从 G1 比赛名列表解析 id 集合（低配路径：给只有名字的数据用）。

    race_db：module.umamusume.asset.race_bwiki 模块（含 RaceDB）。传 None 则返回 []。
    """
    if race_db is None:
        return []
    try:
        rdb = race_db.RaceDB.get()
        out = []
        for nm in names:
            r = rdb.resolve(nm)
            rid = getattr(r, "id", None)
            if rid is not None and int(rid) not in out:
                out.append(int(rid))
        return out
    except Exception:
        return []


def saddle_points(g1_a: Collection[int], g1_b: Collection[int]) -> Tuple[int, int]:
    """两匹种马重合 G1 的胜鞍：(重合场数, 加分点数)。"""
    sa, sb = set(g1_a), set(g1_b)
    overlap = len(sa & sb)
    return overlap, overlap * G1_COMPATIBILITY_POINTS


def tree_saddles(target_g1: Optional[Collection[int]],
                 parent_pairs: List[Tuple[Optional[Collection[int]],
                                          Optional[Collection[int]]]]) -> dict:
    """继承树胜鞍分解（简化入口，按需扩展）。

    parent_pairs 形如 [(B, C), (B, D), (B, E), (C, F), (C, G)] 共 5 项，
    对应巴哈公式中带「父辈对祖辈/父辈间」的胜鞍项；target_g1 预留（现规则
    目标马自身不算胜鞍来源，仅父辈/祖辈重合计）。
    返回 {'overlaps': [场数×5], 'total': 加分}
    """
    overlaps = []
    for a, b in parent_pairs:
        if not a or not b:
            overlaps.append(0)
            continue
        n, _ = saddle_points(a, b)
        overlaps.append(n)
    return {
        "overlaps": overlaps,
        "total": sum(overlaps) * G1_COMPATIBILITY_POINTS,
    }


# ------------------------------------------------------------------- CLI

if __name__ == "__main__":
    import sys
    print(__doc__)
    sys.exit(0)
