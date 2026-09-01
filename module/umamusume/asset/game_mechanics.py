# -*- coding: utf-8 -*-
"""游戏核心机制查询（运行时**不联网**）——训练/心情/因子/商店/剧本。

数据来源：
    resource/umamusume/data/game_mechanics.json
    （从 NGA 综合攻略 + 因子继承进阶攻略结构化提取）

涵盖：
    - 五维属性 + 训练副属性表
    - 心情倍率（训练/比赛）
    - 比赛距离分类 + 路况修正
    - 跑法说明
    - 因子继承（蓝/粉/绿/白）详细规则 + 继承时机
    - 相性规则（避坑/金奖章/同比赛加成）
    - 三剧本机制（URA/青春杯/巅峰杯）
    - 巅峰杯商店道具完整表（7类36种）
    - 支援卡编成推荐
    - 历战惩罚规则

用法：
    from module.umamusume.asset.game_mechanics import GameMechanics
    gm = GameMechanics.get()
    gm.mood_bonus('绝好调')          # {'train': 0.20, 'race': 0.04}
    gm.train_substats('speed')       # {'primary': 'speed', 'secondary': ['power']}
    gm.distance_class(1600)          # '英里'
    gm.shop_items('训练增益')         # [喇叭小/中/大, 负重, ...]
    gm.shop_item('切れ者')           # {'price': 280, 'effect': '获得切れ者'}
    gm.factor_info('blue')           # 蓝色因子详细规则
    gm.scenario_info('巅峰杯')       # 巅峰杯机制摘要
    gm.affinity_avoid()              # ['樱花进王', '乌拉拉', '丸善斯基']

CLI：
    python module/umamusume/asset/game_mechanics.py --mood
    python module/umamusume/asset/game_mechanics.py --shop
    python module/umamusume/asset/game_mechanics.py --factors
    python module/umamusume/asset/game_mechanics.py --scenarios
"""

import json
import os
import sys
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

MECHANICS_PATH = "resource/umamusume/data/game_mechanics.json"


class GameMechanics(object):
    """游戏核心机制查询（懒加载单例）。"""

    _inst = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst

    def __init__(self):
        with open(MECHANICS_PATH, encoding='utf-8') as f:
            self.data = json.load(f)

    # ------------------------------------------------------------------ 属性

    @property
    def stats(self):
        """五维属性说明。"""
        return self.data['stats']

    @property
    def training(self):
        """训练副属性表。"""
        return self.data['training']

    def train_substats(self, stat):
        """某训练项的主属性+副属性。"""
        return self.data['training'].get(stat)

    # ------------------------------------------------------------------ 心情

    @property
    def mood(self):
        """心情倍率表。"""
        return self.data['mood']

    def mood_bonus(self, mood_name):
        """某心情等级的训练/比赛倍率。"""
        m = self.data['mood'].get(mood_name)
        if not m:
            return None
        return {'train': m['train_bonus'], 'race': m['race_bonus']}

    @property
    def mood_up_methods(self):
        """提升心情的方式。"""
        return self.data['mood_up']

    # ------------------------------------------------------------------ 比赛

    def distance_class(self, distance):
        """根据距离数值返回距离分类。"""
        for name, info in self.data['race_distance'].items():
            mn = info.get('min', 0)
            mx = info.get('max', 99999)
            if mn <= distance <= mx:
                return name
        return None

    @property
    def track_conditions(self):
        """路况修正表。"""
        return self.data['track_condition']

    @property
    def running_styles(self):
        """跑法说明。"""
        return self.data['running_style']

    # ------------------------------------------------------------------ 因子

    @property
    def factors(self):
        """因子继承详细规则。"""
        return self.data['factors']

    def factor_info(self, color):
        """某色因子的详细规则（blue/pink/green/white）。"""
        return self.data['factors'].get(color)

    @property
    def inheritance_timeline(self):
        """三次继承时机的触发规则。"""
        return self.data['inheritance_timing']

    # ------------------------------------------------------------------ 相性

    @property
    def affinity_rules(self):
        """相性规则。"""
        return self.data['affinity_rules']

    def affinity_avoid(self):
        """相性极低需避开的角色。"""
        return self.data['affinity_rules']['avoid']

    # ------------------------------------------------------------------ 剧本

    @property
    def scenarios(self):
        """三剧本机制。"""
        return self.data['scenarios']

    def scenario_info(self, name):
        """某剧本的机制摘要。"""
        key = name
        if name in ('URA', 'ura'):
            key = 'URA'
        elif name in ('青春杯', 'aoharu'):
            key = '青春杯'
        elif name in ('巅峰杯', 'peak'):
            key = '巅峰杯'
        return self.data['scenarios'].get(key)

    # ------------------------------------------------------------------ 商店

    @property
    def peak_cup_shop(self):
        """巅峰杯商店全部道具。"""
        return self.data['peak_cup_shop']

    def shop_items(self, category=None):
        """某类商店道具（不传则返回全部）。"""
        shop = self.data['peak_cup_shop']
        if category:
            return shop.get(category, [])
        result = []
        for cat, items in shop.items():
            for item in items:
                item['category'] = cat
                result.append(item)
        return result

    def shop_item(self, name):
        """按名称查商店道具。"""
        for cat, items in self.data['peak_cup_shop'].items():
            for item in items:
                if name in item['name']:
                    return {**item, 'category': cat}
        return None

    def shop_cheapest(self, max_price=50):
        """价格不超过 max_price 的道具列表。"""
        result = []
        for cat, items in self.data['peak_cup_shop'].items():
            for item in items:
                if item['price'] <= max_price:
                    result.append({**item, 'category': cat})
        result.sort(key=lambda x: x['price'])
        return result

    # ------------------------------------------------------------------ 编成

    @property
    def support_builds(self):
        """支援卡编成推荐。"""
        return self.data['support_card_builds']

    def build_for_distance(self, distance_class):
        """某距离分类的推荐编成。"""
        return self.data['distance_build_recommendation'].get(distance_class)

    # ------------------------------------------------------------------ 惩罚

    @property
    def fatigue_penalty(self):
        """历战惩罚规则。"""
        return self.data['fatigue_penalty']


def _main(argv):
    gm = GameMechanics.get()
    if not argv:
        print("用法: game_mechanics.py [--mood|--shop|--factors|--scenarios|--training|--affinity]")
        return 0

    if '--mood' in argv:
        print("=== 心情倍率 ===")
        for name, info in sorted(gm.mood.items(), key=lambda x: -x[1]['order']):
            print(f"  {name}: 训练{info['train_bonus']:+.0%} 比赛{info['race_bonus']:+.0%}")
        print("\n=== 提升方式 ===")
        for method, info in gm.mood_up_methods.items():
            print(f"  {method}: +{info['steps']}阶 体力:{info['stamina_recover']}")
        return 0

    if '--training' in argv:
        print("=== 训练副属性 ===")
        for stat, info in gm.training.items():
            print(f"  {stat}: 主{info['primary']} 副{'+'.join(info['secondary'])} "
                  f"技能pt:{info['skill_pt']}")
        return 0

    if '--shop' in argv:
        print("=== 巅峰杯商店 ===")
        for cat, items in gm.peak_cup_shop.items():
            print(f"\n【{cat}】")
            for item in items:
                print(f"  {item['price']:>4}￥ {item['name']}: {item['effect']}")
        return 0

    if '--factors' in argv:
        print("=== 因子继承 ===")
        for color, info in gm.factors.items():
            print(f"\n【{info['name']}】{info['desc']}")
            if 'stars' in info:
                for star, val in info['stars'].items():
                    print(f"  {star}星: {val['value']}  ({val['note']})")
            if 'upgrade_cost' in info:
                print(f"  适性升级所需: {info['upgrade_cost']}")
            if 'discount' in info:
                print(f"  技能折扣: {info['discount']}")
            print(f"  规则: {info.get('inherit_rule', '')}")
        print("\n=== 继承时机 ===")
        for t in gm.inheritance_timeline:
            print(f"  {t['timing']}: 蓝={t['blue']} 粉={t['pink']} "
                  f"绿={t['green']} 白={t['white']}")
        return 0

    if '--scenarios' in argv:
        print("=== 三剧本机制 ===")
        for name, info in gm.scenarios.items():
            print(f"\n【{name}】")
            print(f"  训练等级: {info['train_level_up']}")
            if 'inherent_upgrade' in info:
                print(f"  固有升级:")
                for u in info['inherent_upgrade']:
                    print(f"    {u['timing']}: 粉丝{u['fans_need']}"
                          f"({u.get('fans_need_dirt','?')}泥地) {u.get('condition','')}")
            if 'new_mechanics' in info:
                print(f"  新机制: {', '.join(info['new_mechanics'])}")
            if 'shop_refresh' in info:
                print(f"  商店刷新: {info['shop_refresh']}")
        return 0

    if '--affinity' in argv:
        print("=== 相性规则 ===")
        rules = gm.affinity_rules
        print(f"  避开: {rules['avoid']}")
        print(f"  同比赛加成: {rules['same_race_bonus']}")
        print(f"  金奖章比赛: {rules['gold_medal_races']}")
        for tip in rules['tips']:
            print(f"  💡 {tip}")
        return 0

    print("未知参数。可用: --mood --training --shop --factors --scenarios --affinity")
    return 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
