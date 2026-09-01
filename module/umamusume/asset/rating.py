# -*- coding: utf-8 -*-
"""马娘最终评分计算（URA-score 式评价分，运行时**不联网**）。

公式来源：BWIKI「简中评分计算器」页面内嵌 JS（完整移植，含全部系数表）。
配套数据：resource/umamusume/data/skill_upgrade.json（tools/build_rating_data.py 构建，
含 287 个技能家族 / 561 技能、升级链与评价分）。

公式总览：
    评分总计 = 五维总计 + 技能总计
    五维总计 = Σ 五维计算(单项属性)     —— 分段线性系数表，1200 以上另一套高斜率表
    技能总计 = Σ 评价分改(已选技能) + 星级系数×固有技等级 + 180×继承技数量
    评价分改 = round(评价分 × 适性倍率)  —— 按技能「条件限制」命中的跑法/距离适性等级
    竞技场评分 = floor(评分总计 × Π(1+竞技场倍率))（场地/距离/跑法三项适性）
    评级：G(<300) → … → B(8200) → A(10000) → S(14500) → SS(17500) → UG(19600)
          → … → UG1(20000) … UB(≥47600)（URA 剧本评级体系）

关键细节（照搬页面 JS 语义）：
    * 五维计算：value+1 后按 50 分段，前 25 段用 koeffi（0.5~6.9），
      超过 1200 的部分按 10 分段用 ovk（7.888~18.3）；≥1209 的部分基数 3912。
      （页面 JS 对 1201~1208 的处理有 NaN bug，本实现按其意图取 ovk[ovq] 修复）
    * 适性倍率（技能倍率，场地/距离与跑法同表）：
      S/A=1.1, B/C=0.9, D/E/F=0.8, G=0.7
    * 同一技能若同时有跑法+距离条件，两组倍率**相乘**；同组内多个条件取最大。
    * special=1 的技能（固有类）倍率恒为 1。
    * 星级系数：1~2星=120，3~5星=170（乘固有技等级 1~6）。
    * 每个继承技固定 +180 分。

用法：
    from module.umamusume.asset.rating import RatingCalc
    calc = RatingCalc.get()
    calc.stat_score(800)                      # 单项属性评分
    calc.total_rating(speed=800, ..., skills=[...], ...)   # 评分总计
    calc.grade(15000)                         # -> 'S+'
    calc.arena_rating(评分, 场地适性='A', 距离适性='S', 跑法适性='A')

CLI：
    python module/umamusume/asset/rating.py --stat 800
    python module/umamusume/asset/rating.py --total 1000 900 800 700 600 \
        --skills 圆弧 顺时针◎ --inherit 3 --star 5 --unique 3
"""

import json
import math
import os
import sys
import threading

# 允许「直接跑脚本」而不只是被 import
_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

SKILL_UPGRADE_PATH = "resource/umamusume/data/skill_upgrade.json"

# ---------------------------------------------------------------------- 系数表
# 五维计算：50 分段系数（覆盖 0~1250）
_KOFFI = [0.5, 0.8, 1, 1.3, 1.6, 1.8, 2.1, 2.4, 2.6, 2.8, 2.9, 3, 3.1, 3.3,
          3.4, 3.5, 3.9, 4.1, 4.2, 4.3, 5.2, 5.5, 6.6, 6.8, 6.9]

# 超过 1200 部分：10 分段系数
_OVK = [7.888, 8, 8.1, 8.3, 8.4, 8.5, 8.6, 8.8, 8.9, 9, 9.2, 9.3, 9.4, 9.6,
        9.7, 9.8, 10, 10.1, 10.2, 10.3, 10.5, 10.6, 10.7, 10.9, 11, 11.1,
        11.3, 11.4, 11.5, 11.7, 11.8, 11.9, 12.1, 12.2, 12.3, 12.4, 12.6,
        12.7, 12.8, 13, 13.1, 13.2, 13.4, 13.5, 13.6, 13.8, 13.9, 14, 14.1,
        14.3, 14.4, 14.5, 14.7, 14.8, 14.9, 15.1, 15.2, 15.3, 15.5, 15.6,
        15.7, 15.9, 16, 16.1, 16.2, 16.4, 16.5, 16.6, 16.8, 16.9, 17, 17.2,
        17.3, 17.4, 17.6, 17.7, 17.8, 17.9, 18.1, 18.2, 18.3]

# 技能倍率（场地/距离适性 & 跑法适性通用）：S/A=1.1, B/C=0.9, D/E/F=0.8, G=0.7
SKILL_RATE = {'S': 1.1, 'A': 1.1, 'B': 0.9, 'C': 0.9,
              'D': 0.8, 'E': 0.8, 'F': 0.8, 'G': 0.7}

# 竞技场倍率（场地/距离用表 vs 跑法用表）
ARENA_RATE_GROUND = {'S': 0.02, 'A': 0.0, 'B': -0.1, 'C': -0.2,
                     'D': -0.3, 'E': -0.4, 'F': -0.5, 'G': -0.7}
ARENA_RATE_STYLE = {'S': 0.02, 'A': 0.0, 'B': -0.05, 'C': -0.1,
                    'D': -0.15, 'E': -0.2, 'F': -0.25, 'G': -0.3}

# 星级系数：1~2星=120，3~5星=170
STAR_COEFF = {'1': 120, '2': 120, '3': 170, '4': 170, '5': 170}

# 技能「条件限制」关键词 → 跑法/距离（评分计算器的判定关键字，注意是简中服措辞）
_RUN_KEYWORDS = [('领跑', '逃'), ('大逃', '逃'), ('跟前', '先'),
                 ('居中', '差'), ('后追', '追')]
_DIST_KEYWORDS = [('短距离', '短距离'), ('英里', '英里'),
                  ('中距离', '中距离'), ('长距离', '长距离')]

# 评级表（分值降序；页面 JS 的完整表）
_GRADE_TABLE = [
    (47600, 'UB'), (46900, 'UC9'), (46200, 'UC8'), (45400, 'UC7'),
    (44700, 'UC6'), (44000, 'UC5'), (43400, 'UC4'), (42700, 'UC3'),
    (42000, 'UC2'), (41300, 'UC1'), (40700, 'UC'), (40000, 'UD9'),
    (39400, 'UD8'), (38700, 'UD7'), (38100, 'UD6'), (37500, 'UD5'),
    (36800, 'UD4'), (36200, 'UD3'), (35600, 'UD2'), (35000, 'UD1'),
    (34400, 'UD'), (33800, 'UE9'), (33200, 'UE8'), (32700, 'UE7'),
    (32100, 'UE6'), (31500, 'UE5'), (31000, 'UE4'), (30400, 'UE3'),
    (29900, 'UE2'), (29400, 'UE1'), (28800, 'UE'), (28300, 'UF9'),
    (27800, 'UF8'), (27300, 'UF7'), (26800, 'UF6'), (26300, 'UF5'),
    (25800, 'UF4'), (25300, 'UF3'), (24800, 'UF2'), (24300, 'UF1'),
    (23900, 'UF'), (23400, 'UG9'), (23000, 'UG8'), (22500, 'UG7'),
    (22100, 'UG6'), (21600, 'UG5'), (21200, 'UG4'), (20800, 'UG3'),
    (20400, 'UG2'), (20000, 'UG1'), (19600, 'UG'), (19200, 'SS+'),
    (17500, 'SS'), (15900, 'S+'), (14500, 'S'), (12100, 'A+'),
    (10000, 'A'), (8200, 'B+'), (6500, 'B'), (4900, 'C+'), (3500, 'C'),
    (2900, 'D+'), (2300, 'D'), (1800, 'E+'), (1300, 'E'), (900, 'F+'),
    (600, 'F'), (300, 'G+'), (0, 'G'),
]


class RatingCalc(object):
    """评分计算器（懒加载技能表单例；纯函数部分可无数据使用）。"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, skill_path=SKILL_UPGRADE_PATH):
        self.skill_path = skill_path
        self.skills_by_name = {}   # 中文名 -> 技能记录
        self.groups = []

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
        if not os.path.isfile(self.skill_path):
            raise FileNotFoundError(
                "技能升级链数据不存在：%s\n请先运行：python tools/build_rating_data.py"
                % self.skill_path)
        with open(self.skill_path, encoding="utf-8") as f:
            data = json.load(f)
        self.groups = data.get("groups", [])
        self.skills_by_name = {}
        for g in self.groups:
            for m in g["members"]:
                # 同组内高类型（升级/上位）优先覆盖同名基础版
                cur = self.skills_by_name.get(m["name"])
                if cur is None or m["type"] > cur["type"]:
                    self.skills_by_name[m["name"]] = m

    # ------------------------------------------------------------- 五维评分

    @staticmethod
    def stat_score(value):
        """单项属性 → 评分（分段线性；1200 以上高斜率）。"""
        value = max(0, int(value))
        oval = 0
        if value > 1200:
            oval = value - 1200
            value = 1200
        value += 1
        q, r = divmod(value, 50)
        result = 0.0
        for i in range(q):
            result += 50 * _KOFFI[i]
        result += r * _KOFFI[q]
        if oval > 0:
            if oval < 9:
                # 页面 JS 在 ovq==0 时取 ovk[undefined]（NaN bug），按意图修复为 ovk[ovq]
                ovq, ovr = divmod(oval, 10)
                for j in range(ovq):
                    result += 10 * _OVK[j]
                result += ovr * _OVK[ovq]
            else:
                result = 3912
                oval += 1
                ovq, ovr = divmod(oval, 10)
                for j in range(1, ovq):
                    result += math.ceil(10 * _OVK[j])
                result += math.ceil(ovr * _OVK[ovq])
        return int(math.floor(result))

    def stats_total(self, speed=0, stamina=0, power=0, guts=0, wisdom=0):
        """五维总计。"""
        return sum(self.stat_score(v) for v in (speed, stamina, power, guts, wisdom))

    # ------------------------------------------------------------- 技能评分

    @staticmethod
    def skill_mult(condition, run_grade=None, dist_grade=None):
        """按「条件限制」与跑法/距离适性等级算技能倍率。

        同组条件取最大，跨组（跑法×距离）相乘；无命中返回 1。
        grade 传 'S'/'A'/…；对应项不适用的跑法/距离可传 None。
        """
        if not condition:
            return 1.0
        temp, temp1 = 1.0, 1.0
        typ = 0
        for kw, _slot in _RUN_KEYWORDS:
            if kw in condition:
                rate = SKILL_RATE.get(run_grade, 1.0) if run_grade else 1.0
                if typ != 2:
                    temp *= rate
                    typ = 2
                else:
                    temp1 = max(temp1, rate)
        for kw, _slot in _DIST_KEYWORDS:
            if kw in condition:
                rate = SKILL_RATE.get(dist_grade, 1.0) if dist_grade else 1.0
                if typ != 3:
                    temp *= rate
                    typ = 3
                else:
                    temp1 = max(temp1, rate)
        return max(temp, temp1)

    def skill_score(self, name, run_grade=None, dist_grade=None):
        """单个技能的评分贡献（round(评价分 × 倍率)）；未收录返回 0。"""
        sk = self.skills_by_name.get(name)
        if sk is None:
            return 0
        if sk.get("special") == 1:
            return int(round(sk["score"]))
        return int(round(sk["score"] * self.skill_mult(
            sk.get("condition", ""), run_grade, dist_grade)))

    def skills_total(self, skills, run_grade=None, dist_grade=None,
                     star=3, unique_level=1, inherit_count=0):
        """技能总计 = Σ评价分改 + 星级系数×固有技等级 + 180×继承技数量。

        skills: 技能名列表（应已去除同组下位重复——同组只算最高版本）。
        """
        subtotal = sum(self.skill_score(s, run_grade, dist_grade) for s in skills)
        star_coeff = STAR_COEFF.get(str(star), 170)
        return subtotal + star_coeff * int(unique_level) + 180 * int(inherit_count)

    # --------------------------------------------------------------- 总分

    def total_rating(self, speed=0, stamina=0, power=0, guts=0, wisdom=0,
                     skills=(), run_grade=None, dist_grade=None,
                     star=3, unique_level=1, inherit_count=0):
        """评分总计 = 五维总计 + 技能总计。"""
        return (self.stats_total(speed, stamina, power, guts, wisdom)
                + self.skills_total(skills, run_grade, dist_grade,
                                    star, unique_level, inherit_count))

    @staticmethod
    def grade(score):
        """评分 → 评级（G~UB）。"""
        for threshold, name in _GRADE_TABLE:
            if score >= threshold:
                return name
        return 'G'

    @staticmethod
    def arena_rating(score, ground_grade='A', dist_grade='A', style_grade='A'):
        """竞技场评分 = floor(评分 × Π(1+竞技场倍率))。

        ground_grade: 场地适性（草/泥同表）；dist_grade: 距离适性；style_grade: 跑法适性。
        """
        coeff = ((1 + ARENA_RATE_GROUND.get(ground_grade, 0))
                 * (1 + ARENA_RATE_GROUND.get(dist_grade, 0))
                 * (1 + ARENA_RATE_STYLE.get(style_grade, 0)))
        return int(math.floor(score * coeff))

    # --------------------------------------------------------------- 辅助

    def skill_pt(self, skills):
        """已选技能的技能点消耗合计（负面紫色技能不计，与页面一致）。"""
        total = 0
        for s in skills:
            sk = self.skills_by_name.get(s)
            if sk and sk.get("color") != "紫色":
                total += sk.get("pt", 0)
        return total

    def skill_info(self, name):
        """查技能记录（评价分/PT/条件限制/升级链位置）。"""
        return self.skills_by_name.get(name)


# ----------------------------------------------------------------------- CLI

def _main(argv):
    calc = RatingCalc.get()
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == '--stat':
        for v in argv[1:]:
            print('stat_score(%s) = %d' % (v, calc.stat_score(int(v))))
        return 0
    if argv[0] == '--total':
        vals = [int(x) for x in argv[1:6]] + [0] * 5
        kw = dict(zip(('speed', 'stamina', 'power', 'guts', 'wisdom'), vals[:5]))
        opts = {}
        for i, a in enumerate(argv):
            if a == '--skills':
                opts['skills'] = argv[i + 1].split(',') if argv[i + 1] else []
            elif a == '--run':
                opts['run_grade'] = argv[i + 1]
            elif a == '--dist':
                opts['dist_grade'] = argv[i + 1]
            elif a == '--star':
                opts['star'] = int(argv[i + 1])
            elif a == '--unique':
                opts['unique_level'] = int(argv[i + 1])
            elif a == '--inherit':
                opts['inherit_count'] = int(argv[i + 1])
        stats = calc.stats_total(**kw)
        skills = opts.get('skills', [])
        sk_total = calc.skills_total(skills, opts.get('run_grade'),
                                     opts.get('dist_grade'),
                                     opts.get('star', 3),
                                     opts.get('unique_level', 1),
                                     opts.get('inherit_count', 0))
        total = stats + sk_total
        print('五维总计 = %d' % stats)
        print('技能总计 = %d (技能点 %d)' % (sk_total, calc.skill_pt(skills)))
        print('评分总计 = %d  评级 = %s' % (total, calc.grade(total)))
        print('距B(8200) = %d  距S(14500) = %d' % (8200 - total, 14500 - total))
        return 0
    if argv[0] == '--skill':
        for name in argv[1:]:
            sk = calc.skill_info(name)
            print(name, '->', json.dumps(sk, ensure_ascii=False) if sk else '(未收录)')
        return 0
    print('未知参数；支持 --stat / --total / --skill')
    return 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
