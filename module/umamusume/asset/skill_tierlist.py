# -*- coding: utf-8 -*-
"""技能推荐分级查询（运行时**不联网**）——S/A/B/C/D/F 分级 + 距离×跑法矩阵。

数据来源：
    resource/umamusume/data/skill_tierlist.json
    （综合 B站全技能分级一图流 + NGA秋月牧场G佬技能选择攻略 + skill_bwiki.json）

涵盖 7 大类：
    - 回复技能（蓝色）：圆弧艺术家/营养补给/深呼吸/放学后的乐趣...
    - 速度技能（黄色）：弯道/直线 × 跑法/距离 矩阵
    - 加速度技能（黄色）：地固/一鼓作气/乘换/豪脚/迅速果断...
    - 出闸技能（黄色）：金集中力/集中力
    - 绿色被动：右转/良马场/距离适性/晴天/一匹狼/诀窍...
    - 减益技能（红色）：魅惑/独占力/踌躇/八方...
    - 继承固有：丸善/莱恩/星云/神鹰/大树/小栗帽/皇帝...

用法：
    from module.umamusume.asset.skill_tierlist import SkillTierList
    tl = SkillTierList.get()
    tl.tier_list('recovery')             # 回复技能分级
    tl.tier_list('acceleration', 'S')    # S级加速度技能
    tl.matrix('中距离', '差')            # 中距离差马推荐技能组
    tl.all_tiers()                       # 全部分级概览
    tl.skill_principles('speed')         # 速度技能选择原则

CLI：
    python module/umamusume/asset/skill_tierlist.py --recovery
    python module/umamusume/asset/skill_tierlist.py --acc
    python module/umamusume/asset/skill_tierlist.py --green
    python module/umamusume/asset/skill_tierlist.py --matrix 中距离 差
    python module/umamusume/asset/skill_tierlist.py --all
"""

import json
import os
import sys
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

TIERLIST_PATH = "resource/umamusume/data/skill_tierlist.json"

# 7 大类
CATEGORIES = ('recovery', 'speed', 'acceleration', 'gate', 'green', 'debuff', 'inherit')


class SkillTierList(object):
    """技能推荐分级查询（懒加载单例）。"""

    _inst = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst

    def __init__(self):
        with open(TIERLIST_PATH, encoding='utf-8') as f:
            self.data = json.load(f)

    @property
    def tier_definition(self):
        """分级定义。"""
        return self.data['tier_definition']

    def categories(self):
        """所有技能大类。"""
        return CATEGORIES

    def _cat_key(self, category):
        """内部：把 category 映射到 JSON key。"""
        mapping = {
            'recovery': 'recovery_skills',
            'speed': 'speed_skills',
            'acceleration': 'acceleration_skills',
            'gate': 'gate_skills',
            'green': 'green_skills',
            'debuff': 'debuff_skills',
            'inherit': 'inherit_skills',
        }
        return mapping.get(category)

    def tier_list(self, category, tier=None):
        """某类技能的分级列表（可只取某 tier）。"""
        key = self._cat_key(category)
        if not key:
            return None
        cat = self.data[key]
        tl = cat.get('tier_list', {})
        if tier:
            return tl.get(tier, [])
        return tl

    def skill_principles(self, category):
        """某类技能的选择原则。"""
        key = self._cat_key(category)
        if not key:
            return None
        return self.data[key].get('principles', [])

    def all_tiers(self):
        """全部分级概览：{category: {tier: [skill_names]}}。"""
        result = {}
        for cat in CATEGORIES:
            tl = self.tier_list(cat)
            if tl:
                result[cat] = {tier: [s['name'] for s in skills]
                               for tier, skills in tl.items()}
        return result

    def matrix(self, distance, style):
        """按距离×跑法查推荐技能组。"""
        key = '%s_%s' % (distance, style)
        return self.data['distance_style_matrix'].get(key)

    def search(self, name):
        """按技能名搜索所属分级。"""
        for cat in CATEGORIES:
            tl = self.tier_list(cat)
            if not tl:
                continue
            for tier, skills in tl.items():
                for s in skills:
                    if name in s['name'] or (s.get('jp') and name in s['jp']):
                        return {'category': cat, 'tier': tier, **s}
        return None


def _main(argv):
    tl = SkillTierList.get()
    if not argv:
        print("用法: skill_tierlist.py [--recovery|--speed|--acc|--gate|--green|--debuff|--inherit]")
        print("      skill_tierlist.py --matrix <距离> <跑法>  (如: 中距离 差)")
        print("      skill_tierlist.py --all")
        print("      skill_tierlist.py --search <技能名>")
        return 0

    cat_flags = {
        '--recovery': 'recovery', '--speed': 'speed', '--acc': 'acceleration',
        '--gate': 'gate', '--green': 'green', '--debuff': 'debuff',
        '--inherit': 'inherit',
    }

    for flag, cat in cat_flags.items():
        if flag in argv:
            print("=== %s 技能分级 ===" % cat)
            principles = tl.skill_principles(cat)
            if principles:
                print("选择原则:")
                for p in principles:
                    print("  • %s" % p)
            tiers = tl.tier_list(cat)
            if tiers:
                for tier in ('S', 'A', 'B', 'C', 'D', 'F'):
                    skills = tiers.get(tier, [])
                    if skills:
                        print("\n[%s级]" % tier)
                        for s in skills:
                            note = s.get('note', '')
                            jp = s.get('jp', '')
                            cond = s.get('cond', '')
                            jp_str = f" ({jp})" if jp else ""
                            cond_str = f" [{cond}]" if cond else ""
                            print("  %s%s%s — %s" % (s['name'], jp_str, cond_str, note))
            return 0

    if '--matrix' in argv:
        idx = argv.index('--matrix')
        if idx + 2 < len(argv):
            distance = argv[idx + 1]
            style = argv[idx + 2]
            result = tl.matrix(distance, style)
            if result:
                print("=== %s × %s 推荐技能 ===" % (distance, style))
                for s in result:
                    print("  • %s" % s)
            else:
                print("未找到 %s × %s 的推荐" % (distance, style))
                print("可用: %s" % ', '.join(tl.data['distance_style_matrix'].keys()))
        return 0

    if '--all' in argv:
        print("=== 全技能分级概览 ===")
        all_t = tl.all_tiers()
        for cat, tiers in all_t.items():
            print(f"\n【{cat}】")
            for tier in ('S', 'A', 'B', 'C', 'D', 'F'):
                if tier in tiers:
                    print(f"  {tier}: {', '.join(tiers[tier])}")
        return 0

    if '--search' in argv:
        idx = argv.index('--search')
        name = argv[idx + 1] if idx + 1 < len(argv) else ''
        result = tl.search(name)
        if result:
            print("找到: %s" % json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("未找到 '%s'" % name)
        return 0

    print("未知参数。可用: --recovery --speed --acc --gate --green --debuff --inherit --matrix --all --search")
    return 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
