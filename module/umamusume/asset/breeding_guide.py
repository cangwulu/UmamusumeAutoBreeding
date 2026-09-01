# -*- coding: utf-8 -*-
"""种马育成方法论查询（运行时**不联网**）——完整流程/因子优先级/配卡/历战路线。

数据来源：
    resource/umamusume/data/breeding_guide.json
    （综合 B站 BV15L4y1w7HD 视频教程 + 多篇图文攻略 + 2025年NGA讨论）

涵盖：
    - 种马定义与目标
    - 完整育成流水线（5步：3蓝→9蓝→历战初代→成品种马→最终成品马）
    - 因子优先级（蓝>粉>白>绿，各色的属性/适性/技能优先序）
    - 剧本选择（URA/青春杯/巅峰杯各自的因子偏向）
    - 技能筛选原则（"蓝绿为主，输出靠固"，T1/T2绿技排行）
    - 历战路线规划（金章比赛清单、最少场次/胜场、历战惩罚规避）
    - 相性优化（避坑角色/同比赛加成/好友借种马/血脉禁忌）
    - 2025年现代种马实践（大赛现搓、白技能卷小技能）

用法：
    from module.umamusume.asset.breeding_guide import BreedingGuide
    bg = BreedingGuide.get()
    bg.pipeline()                    # 完整5步流程
    bg.pipeline_step(3)              # 第3步详情
    bg.factor_priority('blue')       # 蓝色因子优先级
    bg.gold_medal_races()            # 金章比赛清单
    bg.skill_tier('green', 'T1')     # T1级绿技列表
    bg.affinity_avoid()              # 相性避坑角色
    bg.scenario_for_breeding()       # 种马育成剧本推荐

CLI：
    python module/umamusume/asset/breeding_guide.py --pipeline
    python module/umamusume/asset/breeding_guide.py --factors
    python module/umamusume/asset/breeding_guide.py --skills
    python module/umamusume/asset/breeding_guide.py --route
"""

import json
import os
import sys
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

GUIDE_PATH = "resource/umamusume/data/breeding_guide.json"


class BreedingGuide(object):
    """种马育成方法论查询（懒加载单例）。"""

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

    # ------------------------------------------------------------------ 流水线

    @property
    def definition(self):
        """种马定义。"""
        return self.data['definition']

    def pipeline(self):
        """完整5步育成流水线。"""
        return self.data['breeding_pipeline']['steps']

    def pipeline_step(self, step_num):
        """某一步的详情。"""
        for s in self.data['breeding_pipeline']['steps']:
            if s['step'] == step_num:
                return s
        return None

    # ------------------------------------------------------------------ 因子

    @property
    def factor_priorities(self):
        """全部因子优先级。"""
        return self.data['factor_priority']

    def factor_priority(self, color):
        """某色因子优先级（blue/pink/white/green）。"""
        return self.data['factor_priority'].get(color)

    # ------------------------------------------------------------------ 剧本

    @property
    def scenarios(self):
        """种马育成剧本推荐。"""
        return self.data['scenario_choice']

    def scenario_for_breeding(self):
        """种马育成的剧本推荐摘要。"""
        return self.data['scenario_choice']

    # ------------------------------------------------------------------ 技能

    @property
    def skill_filtering(self):
        """技能筛选原则。"""
        return self.data['skill_filtering']

    def skill_tier(self, color, tier):
        """某色技能的某Tier排行（如 green/T1）。"""
        cat = self.data['skill_filtering'].get(color + '_skills')
        if not cat:
            return None
        return cat.get(tier)

    # ------------------------------------------------------------------ 历战

    @property
    def racing_route(self):
        """历战路线规划。"""
        return self.data['racing_route_for_breeding']

    def gold_medal_races(self):
        """金章比赛清单。"""
        return self.data['racing_route_for_breeding']['gold_medal_races']

    # ------------------------------------------------------------------ 相性

    @property
    def affinity(self):
        """相性优化规则。"""
        return self.data['affinity_optimization']

    def affinity_avoid(self):
        """相性避坑角色。"""
        return self.data['affinity_optimization']['avoid']

    # ------------------------------------------------------------------ 现代实践

    @property
    def modern_practice(self):
        """2025年现代种马实践。"""
        return self.data.get('modern_practice_2025', {})


def _main(argv):
    bg = BreedingGuide.get()
    if not argv:
        print("用法: breeding_guide.py [--pipeline|--factors|--skills|--route|--affinity|--modern]")
        return 0

    if '--pipeline' in argv:
        print("=== 种马育成流水线 ===")
        print(f"目标: {bg.definition['goal']}")
        print(f"比喻: {bg.definition['analogy']}")
        for s in bg.pipeline():
            print(f"\n第{s['step']}步: {s['name']}")
            print(f"  方法: {s['method']}")
            if 'tips' in s:
                for t in s['tips']:
                    print(f"  💡 {t}")
            if 'condition' in s:
                print(f"  条件: {s['condition']}")
        return 0

    if '--factors' in argv:
        print("=== 因子优先级 ===")
        for color in ('blue', 'pink', 'white', 'green'):
            info = bg.factor_priority(color)
            if not info:
                continue
            print(f"\n【{color}因子】 优先级#{info['rank']}")
            print(f"  优先序: {info['priority']}")
            print(f"  说明: {info['note']}")
            if 'threshold_3star' in info:
                print(f"  3星阈值: {info['threshold_3star']}")
            if 'S_bonus' in info:
                print(f"  S级加成: {info['S_bonus']}")
            if 'key_skills' in info:
                print(f"  关键技能: {info['key_skills']}")
        return 0

    if '--skills' in argv:
        sf = bg.skill_filtering
        print(f"=== 技能筛选 ===")
        print(f"  核心原则: {sf['core_principle']}")
        print(f"\n【蓝技能】{sf['blue_skills']['desc']}")
        print(f"  必带: {sf['blue_skills']['must_have']}")
        print(f"\n【绿技能】{sf['green_skills']['desc']}")
        print(f"  T1: {sf['green_skills']['T1']}")
        print(f"  T2: {sf['green_skills']['T2']}")
        return 0

    if '--route' in argv:
        rr = bg.racing_route
        print("=== 历战路线规划 ===")
        print(f"  原则: {rr['principle']}")
        print(f"  最少场次: {rr['min_races']} (胜{rr['min_wins']}+)")
        print(f"\n  金章比赛:")
        for g in rr['gold_medal_races']:
            print(f"    {g['name']}: {' + '.join(g['races'])}")
        print(f"\n  Tips:")
        for t in rr['tips']:
            print(f"    💡 {t}")
        return 0

    if '--affinity' in argv:
        af = bg.affinity
        print("=== 相性优化 ===")
        print(f"  避坑: {af['avoid']}")
        print(f"  同比赛: {af['same_race_bonus']}")
        print(f"  金奖章: {af['gold_medal']}")
        print(f"  最佳实践: {af['best_practice']}")
        print(f"  禁忌: {af['taboo']}")
        return 0

    if '--modern' in argv:
        mp = bg.modern_practice
        print("=== 2025现代种马实践 ===")
        print(f"  范式转变: {mp['paradigm_shift']}")
        print(f"  工作流:")
        for s in mp['workflow']:
            print(f"    {s}")
        print(f"  注: {mp['note']}")
        return 0

    print("未知参数。可用: --pipeline --factors --skills --route --affinity --modern")
    return 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
