# -*- coding: utf-8 -*-
"""用官方拆包数据重建/扩充 affinity.json（相性数据资产）。

数据源：uma-tools（mikumifa/uma-tools，闪耀优俊少女特供版）仓库自带的
国服官方拆包数据库 master.mdb：
  - succession_relation         relation_type -> relation_point（官方全量关系组）
  - succession_relation_member  relation_type -> 成员 chara_id
  - succession_relation_rank    相性等级阈值（1:0-50 三角 / 2:51-150 单圈 / 3:151+ 双圈）
  - text_data(category=6)       chara_id -> 简中角色名

为什么升级（对比结论见 docs/research_umalator_succession_planner.md）：
  BWIKI 网页「简中相性计算器」只收录 792 个关系组 / 84 角色，而官方拆包为
  2133 个关系组 / 95 角色（多 1341 个 1pt 细分关系 + 28 个 8pt S 适性组 +
  9 个新角色），经典组合固定相性分普遍低 3~5 分。同 ID 体系（1001=特别周…）。

合并策略（**非覆盖**，保留 BWIKI 标签）：
  1. 以官方 2133 组为准重建 groups（weight 用官方值）。
  2. 官方 type 与 BWIKI type 同体系（792 组重叠仅 1 处权重不同），对重叠组
     优先搬 BWIKI 的 category/detail 标签；官方独有组给通用标签「细分组」。
  3. characters 取官方 95 角色 + 旧文件里官方缺失的（如有）角色名。
  4. 输出仍兼容 affinity.py 的 AffinityDB（characters/groups/meta）。

用法：
  python tools/build_affinity_from_mdb.py <master.mdb 路径> [--out <json>]
"""
import argparse
import json
import os
import re
import sqlite3
from datetime import date

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_OUT = os.path.join(ROOT, 'resource', 'umamusume', 'data', 'affinity.json')
DEFAULT_OLD = DEFAULT_OUT

_INVISIBLE = re.compile(r'[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2060\ufeff]')


def clean(s):
    return _INVISIBLE.sub('', s).strip() if isinstance(s, str) else s


def main():
    ap = argparse.ArgumentParser(description='从 master.mdb 抽取官方相性数据重建 affinity.json')
    ap.add_argument('mdb', help='master.mdb 路径（uma-tools 仓库自带）')
    ap.add_argument('--out', default=DEFAULT_OUT, help='输出 json 路径')
    ap.add_argument('--no-merge-old', action='store_true',
                    help='不读旧 affinity.json（只从官方生成）')
    args = ap.parse_args()

    conn = sqlite3.connect(args.mdb)

    # --- 官方关系组权重 ---
    rel_points = {int(t): int(p) for t, p in
                  conn.execute('SELECT relation_type, relation_point FROM succession_relation')}
    # --- 官方角色归属 ---
    members = {}
    for rt, cid in conn.execute('SELECT relation_type, chara_id FROM succession_relation_member'):
        members.setdefault(int(rt), []).append(int(cid))
    # --- 官方角色名 ---
    name_by_id = {int(idx): clean(text) for idx, text in
                  conn.execute('SELECT [index], text FROM text_data WHERE category=6')}
    conn.close()

    # 官方 groups（只保留 ≥2 成员的组；1 人组不影响两两/三三打分）
    groups = []
    for rt, point in sorted(rel_points.items()):
        mem = sorted(set(members.get(rt, [])))
        if len(mem) < 2:
            continue
        groups.append({'type': rt, 'point': point,
                       'category': '', 'detail': '', 'members': mem})

    # 官方 characters（按名去重、过滤无名字）
    chars = {str(cid): name_by_id.get(cid, '') for g in groups for cid in g['members']}
    chars = {k: v for k, v in chars.items() if v}
    chars = dict(sorted(chars.items(), key=lambda kv: int(kv[0])))

    # --- 读旧文件：搬 BWIKI 的 category/detail 标签 ---
    old_groups, old_chars = {}, {}
    if os.path.isfile(args.out) and not args.no_merge_old:
        with open(args.out, encoding='utf-8') as f:
            old = json.load(f)
        old_groups = {g['type']: g for g in old.get('groups', [])}
        old_chars = old.get('characters', {})

    new_groups = []
    for g in groups:
        old = old_groups.get(g['type'])
        if old:
            g['category'] = old.get('category', '')
            g['detail'] = old.get('detail', '')
        new_groups.append(g)

    # 旧角色补漏（官方没有但旧文件有——理论不会发生，防御）
    for k, v in old_chars.items():
        if k not in chars and clean(v):
            chars[str(k)] = clean(v)
    chars = dict(sorted(chars.items(), key=lambda kv: int(kv[0])))

    n_grp = len(new_groups)
    n_grp_full = len(rel_points)
    from collections import Counter
    pts = Counter(g['point'] for g in new_groups)
    out = {
        'meta': {
            'source': '游戏拆包 master.mdb（succession_relation 官方全量）+ BWIKI 简中相性计算器（标签）',
            'mdb_note': 'master.mdb 来源：mikumifa/uma-tools（闪耀优俊少女特供版）国服官方拆包',
            'upgraded': str(date.today()),
            'relation_types_total': n_grp_full,
            'group_count': n_grp,
            'point_distribution': dict(sorted(pts.items())),
            'character_count': len(chars),
            'rank': {'1': '0-50 三角', '2': '51-150 单圈', '3': '151+ 双圈'},
            'method': {
                'pair_score': '两角色固定相性分 = 两者共同所在关系组的 point 之和',
                'triple_score': '三角色固定相性分 = 三者共同所在关系组的 point 之和',
                'inherit_tree': '目标马(0)/父母1(1)/父母2(2)/祖父母1~4(3~6)；1号=组(0,1)；2号=组(0,2)+组(1,2)；3号=组(0,1,3)；4号=组(0,1,4)；5号=组(0,2,5)；6号=组(0,2,6)；祖父母与目标马同角色时该号记 0 分',
                'grade': '△ 0-50 / 〇 51-150 / ⌾ ≥151',
                'win_saddle_note': '本数据不含胜鞍加成：现行规则(2023-02-24 改版后)仅 G1 胜鞍重合计分、父辈之间也计、无金章加成，需另行按赛程计算（见 stud_planner 胜鞍模块）',
            },
        },
        'characters': chars,
        'groups': new_groups,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('written %s' % args.out)
    print('characters: %d  groups: %d (官方全量 %d, 1人组剔除 %d)  point分布: %s' % (
        len(chars), n_grp, n_grp_full, n_grp_full - n_grp, dict(sorted(pts.items()))))


if __name__ == '__main__':
    main()
