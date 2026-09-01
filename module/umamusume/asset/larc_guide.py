# -*- coding: utf-8 -*-
"""凯旋门剧本（Project L'Arc）攻略查询（运行时**不联网**）。

数据来源：
    resource/umamusume/data/larc_guide.json
    （综合 B站 BV1zxts6zEsi 视频教程 + NGA讨论 + 官方介绍 + 腾讯频道实战）

涵盖：
    - 剧本概览（最短剧本/强制适性/link角色/友人卡必带）
    - 核心机制（群星槽/SS对决赛/赞助者Pt/期待度/海外适应性/交流赛/远征/凯旋门赏魔咒）
    - 完整时间线（三年关键节点）
    - 配卡推荐（速/根/智/友人 + 平替方案）
    - 属性目标（各年凯旋门赏前需达成的面板）
    - 实战流程（序盘/中盘/终盘策略）

用法：
    from module.umamusume.asset.larc_guide import LArcGuide
    lg = LArcGuide.get()
    lg.overview                    # 剧本概览
    lg.mechanic('star_slot')       # 群星槽机制
    lg.mechanic('curse')           # 魔咒机制
    lg.timeline                    # 三年时间线
    lg.card_build                  # 配卡推荐
    lg.stat_targets                # 属性目标
    lg.strategy_flow               # 实战流程

CLI：
    python module/umamusume/asset/larc_guide.py --overview
    python module/umamusume/asset/larc_guide.py --mechanics
    python module/umamusume/asset/larc_guide.py --timeline
    python module/umamusume/asset/larc_guide.py --cards
    python module/umamusume/asset/larc_guide.py --stats
    python module/umamusume/asset/larc_guide.py --strategy
"""

import json
import os
import sys
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

GUIDE_PATH = "resource/umamusume/data/larc_guide.json"


class LArcGuide(object):
    """凯旋门剧本攻略查询（懒加载单例）。"""

    _inst = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst

    def __init__(self):
        with open(GUIDE_PATH, encoding='utf-8') as f:
            self.data = json.load(f)

    @property
    def overview(self):
        return self.data['overview']

    @property
    def mechanics(self):
        return self.data['mechanics']

    def mechanic(self, key):
        """查某项机制（star_slot/ss_showdown/sponsor_pt/expectation/
        adaptability/exchange_races/overseas_expedition/arc_race）。"""
        return self.data['mechanics'].get(key)

    @property
    def timeline(self):
        return self.data['timeline']

    @property
    def card_build(self):
        return self.data['card_build']

    @property
    def stat_targets(self):
        return self.data['stat_targets']

    @property
    def strategy_flow(self):
        return self.data['strategy_flow']


def _main(argv):
    lg = LArcGuide.get()
    if not argv:
        print("用法: larc_guide.py [--overview|--mechanics|--timeline|--cards|--stats|--strategy]")
        return 0

    if '--overview' in argv:
        ov = lg.overview
        print("=== 凯旋门剧本概览 ===")
        print(f"  名称: {ov['name_zh']} ({ov['name_jp']})")
        print(f"  时长: {ov['length']}")
        print(f"  目标: {ov['core_goal']}")
        print(f"  强制适性: {ov['forced_aptitude']}")
        print(f"  Link角色: {ov['link_chars']}")
        print(f"  海外劲敌: {ov['overseas_rivals']}")
        print(f"  必带友人: {ov['friend_card_mandatory']}")
        return 0

    if '--mechanics' in argv:
        m = lg.mechanics
        for key, info in m.items():
            print(f"\n【{info['name']}】")
            desc = info.get('desc', '')
            if desc:
                print(f"  {desc}")
            if 'effect' in info:
                print(f"  效果: {info['effect']}")
            if 'benefits' in info:
                print(f"  收益: {info['benefits']}")
            if 'strategy' in info:
                print(f"  策略: {info['strategy']}")
            if 'levels' in info:
                print(f"  等级:")
                for lv, eff in info['levels'].items():
                    print(f"    {lv}: {eff}")
            if 'categories' in info:
                print(f"  分类: {info['categories']}")
            if 'curse' in info:
                c = info['curse']
                print(f"  魔咒: {c['y2']}")
                print(f"  破除: {c['y3']}")
                print(f"  提示: {c['tip']}")
            if 'features' in info:
                print(f"  特点:")
                for f in info['features']:
                    print(f"    • {f}")
            if 'note' in info:
                print(f"  注: {info['note']}")
        return 0

    if '--timeline' in argv:
        tl = lg.timeline
        for year_key in ('year_1', 'year_2', 'year_3'):
            print(f"\n=== {year_key.replace('_', ' 第').title()} ===")
            for entry in tl[year_key]:
                note = f" ({entry['note']})" if 'note' in entry else ""
                print(f"  {entry['timing']}: {entry['event']}{note}")
        return 0

    if '--cards' in argv:
        cb = lg.card_build
        print("=== 配卡推荐 ===")
        print(f"  必带: {cb['mandatory']}")
        for role, desc in cb['recommended'].items():
            print(f"  {role}: {desc}")
        print(f"\n  平替方案:")
        for role, desc in cb['budget_alternatives'].items():
            print(f"    {role}: {desc}")
        print(f"  种马: {cb['breeding_partner']}")
        return 0

    if '--stats' in argv:
        st = lg.stat_targets
        print("=== 属性目标 ===")
        for key, info in st.items():
            if key == 'tip':
                continue
            print(f"\n  {key}:")
            for k, v in info.items():
                if k != 'note':
                    print(f"    {k}: {v}")
            if 'note' in info:
                print(f"    注: {info['note']}")
        print(f"\n  💡 {st.get('tip', '')}")
        return 0

    if '--strategy' in argv:
        sf = lg.strategy_flow
        for phase in ('early_game', 'mid_game', 'late_game'):
            label = {'early_game': '序盘', 'mid_game': '中盘', 'late_game': '终盘'}[phase]
            print(f"\n=== {label} ===")
            for item in sf[phase]:
                print(f"  • {item}")
        print(f"\n=== 关键要点 ===")
        for item in sf['key_points']:
            print(f"  💡 {item}")
        return 0

    print("未知参数。可用: --overview --mechanics --timeline --cards --stats --strategy")
    return 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
