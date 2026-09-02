# -*- coding: utf-8 -*-
"""种马缺口规划器（StudPlanner）—— 从「下次大赛」倒推「我还差多远」。

输入：
    1) 大赛赛道条件（场地 / 距离 / 草地泥地 / 左右回 / 天气 / 马场状态）
    2) 我的库存（my_inventory/my_characters.csv 马娘、my_support_cards.csv 协助卡、
                 my_studs.csv 已成品种马，模板由 tools/gen_inventory_template.py 生成）

输出：
    主力马目标规格 → 候选马娘排序 → 因子需求(蓝/粉/白/绿) → 现有种马供给 → 缺口
    → 多代养成计划（每代练谁 / 属性目标 / 适性目标 / 赛程 / 配卡 / 关键技能）

术语（见 docs/strategy_integrated.md C 节）：
    * 种马 = 已育成结束、可被后代继承因子的马娘（每次育成选 2 位，加双方祖辈共 6 匹）
    * 蓝因子=属性(3星21/2星12/1星5)，粉因子=适性改造，绿因子=继承固有，白因子=技能/比赛/剧本

用法（库）：
    from module.umamusume.asset.stud_planner import Track, load_inventory, plan
    t = Track(venue='中山', distance=2500, track='草地', direction='右',
              weather='晴', condition='良')
    inv = load_inventory()
    result = plan(t, inv, style='差')

CLI（无需 bot / cv2 环境）：
    python module/umamusume/asset/stud_planner.py --venue 中山 --distance 2500 \
        --track 草地 --direction 右 --weather 晴 --condition 良 [--style 差] [--top 5]
    python module/umamusume/asset/stud_planner.py --race 中山大奖赛
    python module/umamusume/asset/stud_planner.py --inventory-check
"""

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field

from module.umamusume.name_resolver import get_resolver
from typing import Dict, List, Optional, Tuple

# 项目根入 sys.path（本文件在 <根>/module/umamusume/asset/ 下，往上 3 层）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_ASSET_DIR = os.path.join(_PROJECT_ROOT, "module", "umamusume", "asset")
_DATA_DIR = os.path.join(_PROJECT_ROOT, "resource", "umamusume", "data")
DEFAULT_INVENTORY = os.path.join(_PROJECT_ROOT, "my_inventory")

# ============================ 常量 ============================

# 距离分档（game_mechanics.json race_distance）
DIST_RANGES: List[Tuple[str, int, int]] = [
    ("短距离", 0, 1399),
    ("英里", 1400, 1799),
    ("中距离", 1800, 2400),
    ("长距离", 2401, 99999),
]

# 跑法简称（本模块内部统一用单字）↔ 各种写法
STYLE_SHORT = ("逃", "先", "差", "追")
STYLE_FULL = {"逃": "逃马", "先": "先行", "差": "差马", "追": "追马"}
# character_bwiki 的「跑法适应性」字段名
STYLE_TO_APT = {"逃": "领跑", "先": "跟前", "差": "居中", "追": "后追"}
# 反查：用户可能写全名
STYLE_ALIAS = {"逃马": "逃", "领跑": "逃", "逃": "逃",
               "先行": "先", "跟前": "先", "先": "先",
               "差马": "差", "居中": "差", "差": "差",
               "追马": "追", "后追": "追", "追": "追"}

# 适性等级
APT_RANK = {"G": 0, "F": 1, "E": 2, "D": 3, "C": 4, "B": 5, "A": 6, "S": 7}
APT_SCORE = {"S": 100, "A": 85, "B": 70, "C": 50, "D": 30, "E": 15, "F": 5, "G": 0}
RANK_APT = {v: k for k, v in APT_RANK.items()}

# 粉因子：提升 N 阶段所需的累计星数（game_mechanics.json factors.pink.upgrade_cost）
PINK_COST = {0: 0, 1: 1, 2: 4, 3: 7, 4: 10}
# 蓝因子价值
BLUE_VALUE = {3: 21, 2: 12, 1: 5}

# 马场状态修正（game_mechanics.json track_condition）
COND_MOD = {"良": (1.0, 1.0), "稍重": (1.05, 0.95),
            "重": (1.10, 0.90), "不良": (1.15, 0.85)}
COND_ALIAS = {"良场": "良", "稍重场": "稍重", "重场": "重", "不良场": "不良"}

# 耐力需求经验表（草地良场、含常规回蓝技能；社区经验值，非精确模拟）
# 格式：(距离, {跑法: 耐力})
STAMINA_TABLE: List[Tuple[int, Dict[str, int]]] = [
    (1200, {"逃": 420, "先": 400, "差": 370, "追": 350}),
    (1600, {"逃": 600, "先": 570, "差": 530, "追": 500}),
    (2000, {"逃": 800, "先": 760, "差": 710, "追": 680}),
    (2400, {"逃": 950, "先": 900, "差": 850, "追": 800}),
    (3000, {"逃": 1150, "先": 1100, "差": 1030, "追": 980}),
    (3200, {"逃": 1220, "先": 1160, "差": 1090, "追": 1030}),
]

# 力量需求基准（短英距离靠力量加速争位，长距离需求低）
POWER_BASE = {"短距离": 1000, "英里": 900, "中距离": 800, "长距离": 700}
# 智力 / 根性基准
WISDOM_BASE = {"短距离": 650, "英里": 700, "中距离": 700, "长距离": 750}
GUTS_BASE = {"短距离": 350, "英里": 400, "中距离": 450, "长距离": 500}

# 无继承、中等偏上配卡的自练可达基线（用于算蓝因子要补多少）
SELF_BASELINE = {"speed": 1100, "stamina": 600, "power": 700,
                 "wisdom": 600, "guts": 350}

STAT_CN = {"speed": "速度", "stamina": "耐力", "power": "力量",
           "guts": "根性", "wisdom": "智力"}

# 各距离档看重的成长属性
DIST_FOCUS = {"短距离": ("speed", "power"), "英里": ("speed", "wisdom"),
              "中距离": ("speed", "power"), "长距离": ("speed", "stamina")}

# 配卡配比（game_mechanics.json distance_build_recommendation / support_card_builds）
DIST_BUILD = {"短距离": "速智", "英里": "速智", "中距离": "速力", "长距离": "速耐"}
TYPE_MIX = {
    "速智": {"速度": 3, "智力": 2, "友人": 1},
    "速力": {"速度": 3, "力量": 2, "友人": 1},
    "速耐": {"速度": 3, "耐力": 2, "友人": 1},
}

# 蓝因子目标优先级（breeding_guide.factor_priority.blue）
BLUE_PRIORITY = ("stamina", "power", "speed", "wisdom", "guts")


# ============================ 数据加载（绕开 asset/__init__ → cv2） ============================

_ASSETS: Dict[str, object] = {}


def _load_asset(name: str):
    """按文件路径加载 asset 下模块，绕开 __init__（其会 import cv2）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_sp_" + name, os.path.join(_ASSET_DIR, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ensure_assets() -> Dict[str, object]:
    """加载并预热依赖资产。

    注意：skill_tierlist / breeding_guide / affinity 用**相对路径**读数据文件，
    依赖 cwd == 项目根，故这里临时 chdir 完成实例化（都是单例，之后不再读盘）。
    """
    global _ASSETS
    if _ASSETS:
        return _ASSETS
    cwd = os.getcwd()
    os.chdir(_PROJECT_ROOT)
    try:
        for name in ("skill_tierlist", "breeding_guide", "affinity",
                     "route_planner", "chara_skills", "race_bwiki"):
            try:
                _ASSETS[name] = _load_asset(name)
            except Exception as exc:  # 单个资产失败不应拖垮整体
                _ASSETS[name] = None
                print("[警告] 资产 %s 加载失败：%s" % (name, exc), file=sys.stderr)
        # 触发懒加载单例（在 cwd == 项目根时读盘）
        for name, cls in (("skill_tierlist", "SkillTierList"),
                          ("breeding_guide", "BreedingGuide"),
                          ("affinity", "AffinityDB")):
            mod = _ASSETS.get(name)
            if mod is not None:
                try:
                    getattr(mod, cls).get()
                except Exception:
                    pass
    finally:
        os.chdir(cwd)
    return _ASSETS


def _asset(name):
    return ensure_assets().get(name)


def load_json(name: str):
    with open(os.path.join(_DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


# ============================ 输入模型 ============================

@dataclass
class Track:
    """大赛赛道条件。"""

    venue: str = ""            # 场地名，如 中山 / 东京
    distance: int = 2000       # 距离（米）
    surface: str = "草地"       # 草地 / 泥地
    direction: str = "右"       # 左 / 右
    weather: str = "晴"         # 晴 / 阴 / 雨 / 雪
    condition: str = "良"       # 良 / 稍重 / 重 / 不良
    name: str = ""             # 比赛名（可选，用于展示）

    def __post_init__(self):
        if self.condition in COND_ALIAS:
            self.condition = COND_ALIAS[self.condition]
        if self.condition not in COND_MOD:
            self.condition = "良"

    @property
    def distance_class(self) -> str:
        for label, lo, hi in DIST_RANGES:
            if lo <= self.distance <= hi:
                return label
        return "中距离"

    @property
    def cond(self) -> Tuple[float, float]:
        """(耐力倍率, 力量倍率)。"""
        return COND_MOD[self.condition]

    def label(self) -> str:
        return "%s%s %dm %s %s回 · %s · %s场" % (
            self.venue, self.surface, self.distance, self.distance_class,
            self.direction, self.weather, self.condition)


@dataclass
class Chara:
    """我拥有的一只马娘（形态级）。"""

    card_name: str
    name: str
    star: int = 3
    awakening: int = 0
    adapt: Dict[str, Dict[str, str]] = field(default_factory=dict)
    growth: Dict[str, int] = field(default_factory=dict)


@dataclass
class Card:
    """我拥有的一张协助卡。"""

    name: str
    chara: str = ""
    type: str = ""
    rarity: str = ""
    limit: int = 0
    level: int = 1
    effects: List[str] = field(default_factory=list)


@dataclass
class Stud:
    """一只已成品种马（带因子）。"""

    name: str = ""
    stats: Dict[str, int] = field(default_factory=dict)
    blue: List[Tuple[str, int]] = field(default_factory=list)   # [(属性, 星)]
    pink: List[Tuple[str, int]] = field(default_factory=list)   # [(适性项, 星)]
    white: List[str] = field(default_factory=list)
    green: str = ""
    g1: List[str] = field(default_factory=list)


@dataclass
class Inventory:
    characters: List[Chara] = field(default_factory=list)
    cards: List[Card] = field(default_factory=list)
    studs: List[Stud] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.characters and not self.cards


# ============================ 库存读取 ============================

def _to_int(v, default=0) -> int:
    try:
        s = str(v).strip()
        if not s:
            return default
        return int(float(s))
    except Exception:
        return default


def _norm(s) -> str:
    return (str(s or "")).strip()


def load_inventory(directory: str = DEFAULT_INVENTORY) -> Inventory:
    """读取 my_inventory/*.csv。名字已在模板里预填，故直接精确匹配，不做模糊。"""
    inv = Inventory()

    # 马娘：用 character_bwiki 补全适性/成长率
    chara_data = {}
    try:
        for c in load_json("character_bwiki.json")["characters"]:
            chara_data[c.get("card_name")] = c
    except Exception:
        pass

    p = os.path.join(directory, "my_characters.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if _norm(row.get("拥有(1/0)")).lower() in ("1", "y", "yes", "是", "true"):
                    src = chara_data.get(_norm(row.get("形态名")), {})
                    adapt = {}
                    for group, items in (src.get("adapt") or {}).items():
                        adapt[group] = {x["item"]: x["grade"] for x in items}
                    growth = {}
                    for k, v in (src.get("growth") or {}).items():
                        growth[k] = _to_int(str(v).replace("%", ""))
                    inv.characters.append(Chara(
                        card_name=_norm(row.get("形态名")),
                        name=_norm(row.get("角色名")) or (src.get("name") or ""),
                        star=_to_int(row.get("星级(1-5)"), 3) or 3,
                        awakening=_to_int(row.get("觉醒等级(0-5)")),
                        adapt=adapt, growth=growth))

    # 协助卡：用 support_card_bwiki 补全类型/稀有度/效果
    card_data = {}
    try:
        for c in load_json("support_card_bwiki.json")["cards"]:
            card_data[c.get("name")] = c
    except Exception:
        pass

    p = os.path.join(directory, "my_support_cards.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if _norm(row.get("拥有(1/0)")).lower() in ("1", "y", "yes", "是", "true"):
                    src = card_data.get(_norm(row.get("卡名")), {})
                    inv.cards.append(Card(
                        name=_norm(row.get("卡名")),
                        chara=_norm(row.get("关联马娘")) or src.get("chara", ""),
                        type=_norm(row.get("类型")) or src.get("type", ""),
                        rarity=_norm(row.get("稀有度")) or src.get("rarity", ""),
                        limit=_to_int(row.get("突破数(0-4)")),
                        level=_to_int(row.get("等级(1-50)"), 1) or 1,
                        effects=(src.get("extra") or {}).get("support_effects", [])))

    # 已成品种马
    p = os.path.join(directory, "my_studs.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                nm = _norm(row.get("种马角色名"))
                if not nm or nm.startswith("示例"):
                    continue
                stats = {}
                for cn, key in (("速度", "speed"), ("耐力", "stamina"),
                                ("力量", "power"), ("根性", "guts"), ("智力", "wisdom")):
                    stats[key] = _to_int(row.get(cn))
                blue = _parse_star_pairs(row.get("蓝因子(如:速度3星,耐力2星)"))
                pink = _parse_star_pairs(row.get("粉因子(如:中距离3星)"))
                white = [_norm(x) for x in
                         _norm(row.get("白因子技能(逗号分隔)")).replace("，", ",").split(",")
                         if _norm(x)]
                g1 = [_norm(x) for x in
                      _norm(row.get("跑过的G1(逗号分隔)")).replace("，", ",").split(",")
                      if _norm(x)]
                inv.studs.append(Stud(name=nm, stats=stats, blue=blue, pink=pink,
                                      white=white, green=_norm(row.get("绿因子(继承固有)")),
                                      g1=g1))
    return inv


def _parse_star_pairs(text) -> List[Tuple[str, int]]:
    """'耐力3星,速度2星' → [('耐力',3), ('速度',2)]。"""
    out = []
    for part in _norm(text).replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        star = 0
        for ch in ("3", "2", "1"):
            if ch + "星" in part:
                star = int(ch)
                break
        label = part.replace("%d星" % star if star else "", "").strip("() （）")
        if label:
            out.append((label, star))
    return out


# ============================ 目标规格推导 ============================

def _interp_stamina(distance: int, style: str) -> int:
    pts = STAMINA_TABLE
    if distance <= pts[0][0]:
        return pts[0][1][style]
    if distance >= pts[-1][0]:
        return pts[-1][1][style]
    for i in range(len(pts) - 1):
        d0, d1 = pts[i][0], pts[i + 1][0]
        if d0 <= distance <= d1:
            v0, v1 = pts[i][1][style], pts[i + 1][1][style]
            return int(round(v0 + (v1 - v0) * (distance - d0) / (d1 - d0)))
    return pts[-1][1][style]


def target_stats(track: Track, style: str) -> Dict[str, int]:
    """主力马五维目标（经验估算，含马场/场地修正）。"""
    stam_mod, pow_mod = track.cond
    dc = track.distance_class
    stam = _interp_stamina(track.distance, style)
    if track.surface == "泥地":
        stam = int(stam * 1.05)
    stam = int(stam * stam_mod)
    power = int(POWER_BASE[dc] / max(pow_mod, 0.5))
    return {
        "speed": 1200,
        "stamina": int(round(stam / 10.0) * 10),
        "power": int(round(power / 10.0) * 10),
        "guts": GUTS_BASE[dc],
        "wisdom": WISDOM_BASE[dc],
    }


def target_aptitudes(track: Track, style: str) -> Dict[str, str]:
    """适性目标：距离 S > 场地 S > 跑法 S。"""
    return {"距离": "S", "场地": "S", "跑法": "S"}


def recommend_skills(track: Track, style: str) -> Dict[str, object]:
    """推荐技能组（距离×跑法矩阵 + 绿技 + 继承固有）。"""
    tl = _asset("skill_tierlist")
    dc = track.distance_class
    out = {"matrix": [], "green": [], "inherit": [], "green_filter": []}
    if tl is None:
        return out
    try:
        inst = tl.SkillTierList.get()
        out["matrix"] = inst.matrix(dc, style) or []
        greens = (inst.data.get("green_skills") or {}).get("tier_list", {})
        # 按赛道条件过滤绿技
        wanted = []
        if track.direction == "右":
            wanted.append("右")
        else:
            wanted.append("左")
        if track.condition == "良":
            wanted.append("良")
        if track.weather == "晴":
            wanted.append("晴")
        wanted.append("距離")
        for tier, skills in greens.items():
            for s in skills:
                nm = s.get("name", "")
                if any(w in nm for w in wanted):
                    out["green"].append({"tier": tier, "name": nm,
                                         "cond": s.get("cond", ""), "note": s.get("note", "")})
        out["green_filter"] = wanted
        inh = (inst.data.get("inherit_skills") or {}).get("tier_list", {})
        for tier, skills in inh.items():
            for s in skills:
                out["inherit"].append({"tier": tier, "name": s.get("name", ""),
                                       "cond": s.get("cond", ""), "note": s.get("note", "")})
    except Exception:
        pass
    return out


def key_white_skills(track: Track, style: str) -> List[str]:
    """该跑法最该从白因子拿的技能。

    白（技能）因子来自「育成时学过的技能」，学**双圈版 / 上位金技**可显著提高产出率。
    故这里直接取距离×跑法矩阵的推荐技能作为目标，再叠加攻略里点名的关键技。
    """
    out: List[str] = []
    matrix = recommend_skills(track, style).get("matrix") or []
    if matrix:
        out.append("本跑法推荐技能（学双圈/金版提高技能因子产出率）：" + "、".join(matrix[:6]))
    bg = _asset("breeding_guide")
    if bg is not None:
        try:
            ks = bg.BreedingGuide.get().factor_priority("white").get("key_skills", {})
            for k, v in ks.items():
                if STYLE_ALIAS.get(k, "") == style or k == "通用":
                    out.append("攻略点名（%s）：%s" % (k, v))
        except Exception:
            pass
    if not out:
        out = [{"逃": "逃马：地固 + 对应绿技 combo", "先": "先行：地固",
                "差": "差马：弧线教授 / 弯道回复",
                "追": "追马：直线一气（一鼓作气）"}.get(style, "")]
    # 通用：剧本因子与比赛因子
    out.append("剧本因子：URA→速耐 / 青春杯→力智 / 巅峰杯→根耐（URA 需赢 3 场 URA 比赛）")
    out.append("比赛因子：只能从 G1 胜鞍产生 → 赛程尽量覆盖 G1")
    return out


# ============================ 候选马娘打分 ============================

def form_skills(chara: "Chara") -> Dict[str, object]:
    """取出马娘某「形态」的真实技能（固有 / 觉醒 / 初始）。

      - 固有 / 觉醒：角色级（上游 pretty-derby 未细分到形态，属上游限制）
      - 初始技能：形态级，且**同一批马的不同形态确实不同** —— 这是本函数要修好的核心点
    """
    cs = _asset("chara_skills")
    out = {"unique": [], "awakening": [], "initial": []}
    if cs is None:
        return out
    try:
        u = cs.unique_skill_of(chara.name)
        if u:
            out["unique"] = [u] if isinstance(u, dict) else list(u)
    except Exception:
        pass
    try:
        aw = cs.awakening_skills_of(chara.name)
        if aw:
            out["awakening"] = list(aw)
    except Exception:
        pass
    try:
        card = _resolve_form_card(chara)
        if card is not None:
            out["initial"] = list(card.get("initial_skills") or [])
        else:
            # 退化：该形态无法单独定位，取全部形态的并集（至少不漏）
            rec = cs.get_db().match(chara.name)[0]
            if rec:
                for c in (rec.get("cards") or []):
                    out["initial"].extend(c.get("initial_skills") or [])
    except Exception:
        pass
    return out


# character_bwiki 的「角色名 -> 该角色全部 BWIKI 形态名（按文件顺序）」缓存。
# 用于把 BWIKI 全形态名定位到 chara_skills 的卡序号（两套卡名是不同本地化翻译，无法直接相等）。
_BWIKI_FORMS_CACHE: Dict[str, List[str]] = {}


def _bwiki_forms_by_role() -> Dict[str, List[str]]:
    global _BWIKI_FORMS_CACHE
    if _BWIKI_FORMS_CACHE:
        return _BWIKI_FORMS_CACHE
    out: Dict[str, List[str]] = {}
    try:
        for c in load_json("character_bwiki.json")["characters"]:
            nm = c.get("name")
            cn = c.get("card_name")
            if nm and cn:
                out.setdefault(nm, []).append(cn)
    except Exception:
        pass
    _BWIKI_FORMS_CACHE = out
    return out


def _resolve_form_card(chara: "Chara"):
    """把 BWIKI 全形态名（如『【无声无瑕】无声铃鹿』）映射到 chara_skills 的「卡」记录。

    统一走 name_resolver：任何表面名 -> 日文形态规范键（chara_skills 的 card_jp
    正是这个键），做到「BWIKI 中文形态名 ↔ pretty-derby 中文形态名 ↔ 日文名」三方精确对应。
    解析层给不出 form 键时（只给了角色名、或两源表单数/顺序错乱），退回位置序号兜底。
    """
    cs = _asset("chara_skills")
    if cs is None:
        return None
    try:
        db = cs.get_db()
    except Exception:
        return None
    rec = db.match(chara.name or "")[0]
    if not rec:
        return None
    cards = rec.get("cards") or []
    if not cards:
        return None

    full = chara.card_name or ""
    # 1) 统一解析层：表面名 -> 日文形态规范键 -> chara_skills 形态卡（精确）
    try:
        r = get_resolver()
        jp_key, _ = r.canonical(full)
        if jp_key and r.kind(jp_key) == "form":
            pair = db._by_card_jp.get(jp_key)
            if pair is not None:
                return pair[1]
    except Exception:
        pass
    # 2) 位置序号兜底（解析层只给到角色级键、或两源表单顺序无法对齐时）
    forms = _bwiki_forms_by_role().get(chara.name or "", [])
    if full and full in forms:
        idx = forms.index(full)
        if 0 <= idx < len(cards):
            return cards[idx]
        return cards[min(idx, len(cards) - 1)]
    # 3) 退化
    return None


def _inherited_unique_fit(chara: "Chara") -> Tuple[int, str]:
    """该「形态」的固有作为「继承固有（绿因子）」的价值分 (0-100, 说明)。

    直接用 chara_skills 取出这个形态所属的固有技能名，再在技能分级表
    （inherit_skills tier_list）里按**精确名**定位其价值档；找不到才退化为模糊匹配。
    """
    cs = _asset("chara_skills")
    uniq_name = ""
    if cs is not None:
        try:
            u = cs.unique_skill_of(chara.name)
            if u:
                uniq_name = u.get("name", "")
        except Exception:
            pass
    tl = _asset("skill_tierlist")
    if tl is not None and uniq_name:
        try:
            inh = (tl.SkillTierList.get().data.get("inherit_skills") or {}).get("tier_list", {})
            for tier, skills in inh.items():
                for s in skills:
                    if s.get("name", "") == uniq_name:
                        return (100 if tier == "S" else 80), "本形态固有「%s」（%s级继承价值）" % (uniq_name, tier)
            for tier, skills in inh.items():
                for s in skills:
                    core = s.get("name", "").replace("固有", "").strip()
                    if core and (core in uniq_name or uniq_name in core):
                        return (100 if tier == "S" else 80), "本形态固有「%s」（近似 %s级）" % (uniq_name, tier)
        except Exception:
            pass
    if uniq_name:
        return 40, "本形态固有「%s」未列入高价值继承列表" % uniq_name
    return 30, "无固有数据"


def score_candidate(chara: Chara, track: Track, style: str) -> Dict[str, object]:
    """给一只马娘在该赛道/跑法下打分（0-100）并给出明细。"""
    dc = track.distance_class
    dist_map = (chara.adapt.get("距离适应性") or {})
    surf_map = (chara.adapt.get("场地适应性") or {})
    style_map = (chara.adapt.get("跑法适应性") or {})

    d_grade = dist_map.get(dc, "G")
    s_grade = surf_map.get(track.surface, "G")
    st_grade = style_map.get(STYLE_TO_APT[style], "G")

    d_score = APT_SCORE.get(d_grade, 0)
    s_score = APT_SCORE.get(s_grade, 0)
    st_score = APT_SCORE.get(st_grade, 0)

    uniq_score, uniq_note = _inherited_unique_fit(chara)

    focus = DIST_FOCUS.get(dc, ("speed",))
    gsum = sum(chara.growth.get(k, 0) for k in focus)
    growth_score = min(100, int(gsum * 2.5))  # 20%+20%=40% 视为满分

    total = (0.35 * d_score + 0.20 * s_score + 0.20 * st_score
             + 0.15 * uniq_score + 0.10 * growth_score)

    return {
        "chara": chara,
        "total": round(total, 1),
        "distance": d_grade, "surface": s_grade, "style": st_grade,
        "uniq_note": uniq_note,
        "skills": form_skills(chara),
        "growth": {STAT_CN.get(k, k): "%d%%" % chara.growth.get(k, 0) for k in focus},
        "parts": {"距离适性": round(0.35 * d_score, 1),
                  "场地适性": round(0.20 * s_score, 1),
                  "跑法适性": round(0.20 * st_score, 1),
                  "固有价值": round(0.15 * uniq_score, 1),
                  "成长率": round(0.10 * growth_score, 1)},
    }


def rank_candidates(inv: Inventory, track: Track, style: str,
                    top: int = 5) -> List[Dict[str, object]]:
    scored = [score_candidate(c, track, style) for c in inv.characters]
    scored.sort(key=lambda x: -x["total"])
    return scored[:top]


# ============================ 因子需求 ============================

def pink_need(current: str, target: str) -> Dict[str, object]:
    """粉因子需求：从 current 适性提到 target 需要多少星、能到哪。

    规则（docs/strategy_integrated.md C.2）：
      * 1 星粉 = +1 阶段；累计 4/7/10 星 = +2/+3/+4 阶段
      * 单项最高 +4 阶段
      * **初始继承封顶 A，到不了 S** —— S 只能靠第二/三次继承的概率触发
    """
    cur, tgt = APT_RANK.get(current, 0), APT_RANK.get(target, 0)
    need = tgt - cur
    if need <= 0:
        return {"stages": 0, "stars": 0, "stages": 0, "initial_reach": current,
                "initial_stages": 0, "prob_stages": 0,
                "note": "已达标，无需粉因子"}
    initial_cap = min(need, APT_RANK["A"] - cur, 4)   # 初始继承最多到 A
    remaining = need - initial_cap
    stars = PINK_COST.get(initial_cap, 10)
    initial_reach = RANK_APT.get(min(cur + initial_cap, APT_RANK["A"]), current)
    if initial_cap == 0:
        note = "已在 %s，初始继承封顶 A 无法再升；%s→%s 只能靠第二/三次继承概率触发" % (
            current, current, target)
    else:
        note = "初始继承 %d 阶段（需 %d 星）→ %s" % (initial_cap, stars, initial_reach)
        if remaining > 0:
            note += "；剩余 %d 阶段（%s→%s）只能靠第二/三次继承概率触发" % (
                remaining, initial_reach, target)
    return {"stages": need, "stars": stars, "initial_reach": initial_reach,
            "initial_stages": initial_cap, "prob_stages": remaining, "note": note}


def factor_requirements(chara: Chara, track: Track, style: str,
                        stats_goal: Dict[str, int]) -> Dict[str, object]:
    """分解一只主力马需要哪些因子。"""
    dc = track.distance_class
    dist_map = (chara.adapt.get("距离适应性") or {})
    surf_map = (chara.adapt.get("场地适应性") or {})
    style_map = (chara.adapt.get("跑法适应性") or {})

    def _pn(label, cur):
        r = pink_need(cur, "S")
        r["current"] = cur
        r["label"] = label
        return r

    pink = {
        "距离(%s)" % dc: _pn(dc, dist_map.get(dc, "G")),
        "场地(%s)" % track.surface: _pn(track.surface, surf_map.get(track.surface, "G")),
        "跑法(%s)" % STYLE_FULL[style]: _pn(STYLE_FULL[style],
                                          style_map.get(STYLE_TO_APT[style], "G")),
    }

    # 属性缺口 = 目标 - 自练基线（只算正缺口）
    # 注意：这不是「全靠蓝因子补」——蓝因子只能补其中一小部分，其余靠配卡训练。
    blue = {}
    for k, goal in stats_goal.items():
        gap = goal - SELF_BASELINE.get(k, 0)
        if gap > 0:
            blue[STAT_CN[k]] = gap
    blue_order = [STAT_CN[k] for k in BLUE_PRIORITY if STAT_CN[k] in blue]

    # 绿因子（继承固有）：首选目标「形态」自身的固有（最终马最该继承的血脉来源），
    # 再叠加距离×跑法矩阵里契合本场比赛的高价值继承固有；排除目标自身（血脉禁忌）。
    cs = _asset("chara_skills")
    own_uniq = ""
    if cs is not None:
        try:
            u = cs.unique_skill_of(chara.name)
            if u:
                own_uniq = u.get("name", "")
        except Exception:
            pass
    green = []
    if own_uniq:
        green.append({"name": own_uniq, "tier": "本形态固有",
                      "cond": "血脉来源（自练即带）", "self": True})
    for g in recommend_skills(track, style)["inherit"]:
        core = g["name"].replace("固有", "").replace("(鲁道夫)", "").strip()
        if core and (core in chara.name or chara.name in core):
            continue
        green.append(g)
    # 排序：目标自身固有永远置顶（血脉来源，最重要），其余按跑法契合度
    def _gk(g):
        if g.get("self"):
            return (-2, 0)   # 负值 → 升序最前
        cond = g.get("cond", "")
        hit = 1 if STYLE_FULL[style][0] in cond else 0
        return (-hit, 0 if g.get("tier") == "S" else 1)
    green.sort(key=_gk)

    return {
        "pink": pink,
        "stat_gap": blue,
        "blue_priority": blue_order,
        "white": key_white_skills(track, style),
        "green": green,
        "self_baseline": {STAT_CN[k]: v for k, v in SELF_BASELINE.items()},
    }


# ============================ 供给与缺口 ============================

def supply_from_studs(studs: List[Stud]) -> Dict[str, object]:
    """汇总现有种马能提供的因子。"""
    blue: Dict[str, int] = {}
    blue_stars: Dict[str, int] = {}
    pink: Dict[str, int] = {}
    white: List[str] = []
    green: List[str] = []
    g1: List[str] = []
    for s in studs:
        for label, star in s.blue:
            blue[label] = blue.get(label, 0) + BLUE_VALUE.get(star, 0)
            blue_stars[label] = blue_stars.get(label, 0) + star
        for label, star in s.pink:
            pink[label] = pink.get(label, 0) + star
        white.extend(s.white)
        if s.green:
            green.append(s.green)
        g1.extend(s.g1)
    return {"count": len(studs), "blue": blue, "blue_stars": blue_stars,
            "pink": pink, "white": sorted(set(white)),
            "green": sorted(set(green)), "g1": sorted(set(g1))}


def _ideal_supply() -> Dict[str, object]:
    """理想配置的供给（9 蓝 + 满粉 + 关键白），用于对比「还差多远」。"""
    return {
        "label": "理想配置（9 蓝因子 + 满粉因子 + 关键白因子）",
        "blue_per_stat": 3 * BLUE_VALUE[3],      # 3 个 3 星同属性
        "blue_total_stars": 9,
        "pink_stars": 10,                         # 单项 +4 阶段
        "white": "关键技能因子（地固 / 直线一气）+ 剧本因子 + 比赛因子",
    }


# ============================ 配卡 / 赛程 ============================

def card_score(card: Card) -> int:
    """卡质量分：稀有度 + 突破 + 效果条数。"""
    base = {"SSR": 100, "SR": 70, "R": 40}.get(card.rarity.upper(), 40)
    return base + card.limit * 12 + min(len(card.effects), 8) * 2


def recommend_deck(inv: Inventory, dc: str, top_n: int = 6) -> Dict[str, object]:
    """按距离档推荐配卡（从拥有的卡里挑）。"""
    build = DIST_BUILD.get(dc, "速智")
    mix = TYPE_MIX.get(build, {"速度": 3, "智力": 2, "友人": 1})
    pool = sorted(inv.cards, key=lambda c: -card_score(c))
    picked: List[Card] = []
    missing: Dict[str, int] = {}
    for ctype, need in mix.items():
        cands = [c for c in pool if c.type == ctype and c not in picked][:need]
        if len(cands) < need:
            missing[ctype] = need - len(cands)
        picked.extend(cands)
    # 缺口用其他类型的次优卡补齐
    if len(picked) < top_n:
        for c in pool:
            if c not in picked:
                picked.append(c)
            if len(picked) >= top_n:
                break
    return {"build": build, "mix": mix, "cards": picked[:top_n], "missing": missing}


def plan_route(chara: Chara, mode: str = "rest:2") -> Dict[str, object]:
    """生成历战路线（用于种马跑 G1 拿白因子 + 胜鞍）。"""
    rp = _asset("route_planner")
    if rp is None:
        return {}
    try:
        chars = rp.load_characters()
        raw = rp.resolve_character(chara.card_name or chara.name, chars)
        if raw is None:
            raw = rp.resolve_character(chara.name, chars)
        if raw is None:
            return {}
        route = rp.generate_route(raw, mode=mode)
        stats = rp.route_stats(route)
        return {"route": route, "stats": stats, "chara": raw}
    except Exception:
        return {}


def gold_medal_hint() -> List[str]:
    """金章组合提示（用于对齐胜鞍 → 加相性分）。日文原名会译成简中权威名。"""
    bg = _asset("breeding_guide")
    if bg is None:
        return []
    raw = []
    try:
        g = bg.BreedingGuide.get().gold_medal_races()
        if isinstance(g, dict):
            raw = list(g.values())
        elif isinstance(g, list):
            raw = g
    except Exception:
        return []
    out = []
    for item in raw:
        name = item.get("name", "") if isinstance(item, dict) else str(item)
        races = item.get("races", []) if isinstance(item, dict) else []
        cn = [_cn_race(r) for r in races]
        out.append("- **%s**：%s" % (name, " + ".join(cn) if cn else "—"))
    return out


# 金章/攻略里常见的**日式写法** → 简中权威名。
# race_bwiki 的 resolve 靠别名表 + cosine 兜底，遇到「半角括号」「天皇賞 vs 天王奖」这类
# 差异会失配，故这里对高频 G1 做一层硬映射（只兜底，不覆盖 resolve 的成功结果）。
_RACE_CN_FALLBACK = {
    "日本ダービー": "东京优骏（全国德比）",
    "日本ダービ": "东京优骏（全国德比）",
    "東京優駿": "东京优骏（全国德比）",
    "天皇賞(春)": "天王奖（春）",
    "天皇賞（春）": "天王奖（春）",
    "天皇賞(秋)": "天王奖（秋）",
    "天皇賞（秋）": "天王奖（秋）",
    "スプリンダーズS": "短途者锦标赛",
    "スプリンターズS": "短途者锦标赛",
    "ジャパンカップ": "全国杯",
    "有馬記念": "中山大奖赛",
    "安田記念": "东京英里赛",
    "高松宮記念": "中京短途赛",
    "マイルチャンピオンシップ": "英里冠军赛",
    "エリザベス女王杯": "伊丽莎白女王杯",
    "皐月賞": "皋月奖",
    "菊花賞": "菊花奖",
    "桜花賞": "樱花奖",
    "オークス": "奥克斯",
    "秋華賞": "秋华奖",
    "宝塚記念": "宝冢纪念",
    "大阪杯": "大阪杯",
    "フェブラリーステークス": "二月锦标赛",
    "チャンピオンズカップ": "全国冠军杯",
    "朝日杯フューチュリティステークス": "朝日杯未来锦标赛",
    "ホープフルステークス": "希望锦标赛",
    "ヴィクトリアマイル": "维多利亚英里赛",
    "NHKマイルカップ": "广播协会英里杯",
}


def _cn_race(name: str) -> str:
    """任意别名（日文/旧中文/繁中/csv id）→ 简中权威名。失败则原样返回。"""
    rb = _asset("race_bwiki")
    if rb is None:
        return _RACE_CN_FALLBACK.get(name, name)
    try:
        # 注意：resolve 是 RaceDB 的方法，不是模块级函数（踩过坑）
        r = rb.RaceDB.get().resolve(name)
        if r is None:
            return _RACE_CN_FALLBACK.get(name, name)
        if isinstance(r, dict):
            return r.get("name") or name
        if isinstance(r, str):
            return r
        # race_bwiki.resolve 返回 Race 对象
        return getattr(r, "name", None) or name
    except Exception:
        return name


# ============================ 主规划流程 ============================

def plan(track: Track, inv: Inventory, style: str = "差",
         top: int = 5) -> Dict[str, object]:
    stats_goal = target_stats(track, style)
    apt_goal = target_aptitudes(track, style)
    skills = recommend_skills(track, style)
    cands = rank_candidates(inv, track, style, top=top)
    supply = supply_from_studs(inv.studs)
    ideal = _ideal_supply()

    details = []
    for c in cands:
        req = factor_requirements(c["chara"], track, style, stats_goal)
        deck = recommend_deck(inv, track.distance_class)
        details.append({"score": c, "requirements": req, "deck": deck})

    return {
        "track": track,
        "style": style,
        "stats_goal": stats_goal,
        "apt_goal": apt_goal,
        "skills": skills,
        "candidates": details,
        "supply": supply,
        "ideal": ideal,
        "inventory_empty": inv.empty,
    }


# ============================ 多代养成计划 ============================

def score_stud_candidate(chara: Chara, track: Track, focus_stat: str) -> Dict[str, object]:
    """种马候选打分（与「主力马打分」不同：种马要能历战 + 把目标属性拉高）。

    权重：目标属性成长 30% / 该距离适性 25% / 历战广度 25% / 场地适性 20%
    """
    adapt = chara.adapt
    dist = (adapt.get("距离适应性") or {})
    surf = (adapt.get("场地适应性") or {})
    dc = track.distance_class
    # 历战广度：适性 ≥ C 的距离档数量（能跑的比赛越多，G1 覆盖越广）
    breadth = sum(1 for g in dist.values() if APT_RANK.get(g, 0) >= APT_RANK["C"])
    breadth_score = min(100.0, breadth / 4.0 * 100)
    surf_score = APT_SCORE.get(surf.get(track.surface, "G"), 0)
    dist_score = APT_SCORE.get(dist.get(dc, "G"), 0)
    growth = chara.growth.get(focus_stat, 0)
    growth_score = min(100.0, growth * 5)
    total = (0.25 * breadth_score + 0.20 * surf_score
             + 0.25 * dist_score + 0.30 * growth_score)
    return {"chara": chara, "total": round(total, 1), "breadth": breadth,
            "surface": surf.get(track.surface, "G"),
            "distance": dist.get(dc, "G"), "growth": growth,
            "focus": STAT_CN.get(focus_stat, focus_stat)}


def _pick_best(pool: List[Chara], used: List[str], track: Track,
               focus_stat: str) -> Optional[Dict[str, object]]:
    """挑未被用过的最佳种马候选（用过的排后面，允许重复但降权）。"""
    if not pool:
        return None
    scored = [score_stud_candidate(c, track, focus_stat) for c in pool]
    scored.sort(key=lambda x: (x["chara"].name in used, -x["total"]))
    return scored[0]


def breeding_plan(inv: Inventory, track: Track, style: str,
                  result: Dict[str, object]) -> Dict[str, object]:
    """按「从零规划」生成多代养成计划，每代指定练谁 / 练什么 / 跑什么 / 带什么卡。

    代际结构（源自 breeding_guide 的 5 步流水线，按实际缺口裁剪）：
        蓝因子代（缺几个属性就几代）→ 历战代（跑 G1 拿白因子+胜鞍）→ 成品参赛马
    血脉禁忌：最终成品马娘不能出现在自己的血脉树里 → 种马角色须避开目标马。
    """
    dc = track.distance_class
    stats_goal = result["stats_goal"]
    gaps = {k: max(0, stats_goal[k] - SELF_BASELINE.get(k, 0)) for k in SELF_BASELINE}
    blue_order = [k for k in BLUE_PRIORITY if gaps.get(k, 0) > 0] or ["stamina", "power"]

    _c0 = result["candidates"][0] if result["candidates"] else None
    target = _c0["score"]["chara"] if _c0 else None
    banned = {target.name} if target else set()
    pool = [c for c in inv.characters if c.name not in banned]
    if not pool:
        return {"generations": [], "note": "库存为空，或没有可作为种马的角色（须避开目标马）",
                "target": target, "blue_order": [STAT_CN[k] for k in blue_order]}

    used: List[str] = []
    gens: List[Dict[str, object]] = []
    deck = recommend_deck(inv, dc)
    white = key_white_skills(track, style)

    # --- 蓝因子代：每代主攻一个缺口属性，冲 1100 出 3 星蓝 ---
    for stat in blue_order[:2]:
        pick = _pick_best(pool, used, track, stat)
        if pick is None:
            break
        ch: Chara = pick["chara"]
        used.append(ch.name)
        route = plan_route(ch, mode="rest:2")
        gens.append({
            "gen": len(gens) + 1,
            "role": "蓝因子种马（第 %d 只）" % (len(gens) + 1),
            "chara": ch,
            "score": pick,
            "focus": STAT_CN[stat],
            "stat_target": {STAT_CN[stat]: 1100},
            "stat_note": "≥600 才可能出 3 星蓝；≥1100 三星概率大幅提高（约 5%→10%）",
            "apt_target": "把要传给后代的适性拉到 A 以上（粉因子只能从 A 以上适性抽取）",
            "route": route.get("stats") or {},
            "route_mode": "2 战 1 休（连跑 3 场会掉心情 + 肌肤干燥）",
            "deck": deck,
            "skills": white[:2],
            "output": "3 星%s蓝因子（初始继承每个 +%d 属性）" % (STAT_CN[stat], BLUE_VALUE[3]),
        })

    # --- 历战代：适性广度优先，大量跑 G1 拿白因子 + 胜鞍 ---
    hist = [score_stud_candidate(c, track, "stamina") for c in pool]
    hist.sort(key=lambda x: (x["chara"].name in used, -x["breadth"], -x["total"]))
    if hist:
        pick = hist[0]
        ch = pick["chara"]
        used.append(ch.name)
        route = plan_route(ch, mode="rest:2")
        gens.append({
            "gen": len(gens) + 1,
            "role": "历战种马（G1 覆盖 + 胜鞍）",
            "chara": ch,
            "score": pick,
            "focus": "比赛数量",
            "stat_target": {},
            "stat_note": "属性不是重点：历战马比赛占训练回合，属性不会高，够赢就行", 
            "apt_target": "适性越广能跑的比赛越多（广度 %d/4 档）" % pick["breadth"],
            "route": route.get("stats") or {},
            "route_mode": "2 战 1 休；尽量覆盖 G1，对齐金章组合",
            "deck": deck,
            "skills": white,
            "output": "白因子（比赛/技能/剧本）+ 胜鞍分（相性加成）",
        })

    # --- 最终代：成品参赛马 ---
    if target is not None:
        gens.append({
            "gen": len(gens) + 1,
            "role": "成品参赛马（目标马娘本人）",
            "chara": target,
            "score": None,
            "focus": "全部",
            "stat_target": {STAT_CN[k]: stats_goal[k] for k in
                            ("speed", "stamina", "power", "guts", "wisdom")},
            "stat_note": "用前面几代做种马（选 2 只 + 各自祖辈共 6 匹）",
            "apt_target": "距离 S / 场地 S / 跑法 S",
            "route": {},
            "route_mode": "按育成目标 + 大赛前目标比赛走，不必历战",
            "deck": deck,
            "skills": (result["skills"].get("matrix") or []),
            "output": "参赛马",
        })

    # --- 相性：目标马与各代种马的固定相性分 ---
    aff = _asset("affinity")
    partner_hint: List[Dict[str, object]] = []
    if aff is not None and target is not None:
        try:
            db = aff.AffinityDB.get()
            for g in gens:
                if g["chara"].name == target.name:
                    continue
                s = db.pair_score(target.name, g["chara"].name)
                g["affinity"] = {"score": s, "grade": db.grade(s),
                                 "note": "固定相性分（不含胜鞍分）"}
            owned = {c.name for c in inv.characters if c.name != target.name}
            scored = []
            for nm in owned:
                try:
                    s = db.pair_score(target.name, nm)
                except Exception:
                    s = 0
                if s:
                    scored.append({"name": nm, "score": s, "grade": db.grade(s)})
            scored.sort(key=lambda x: -x["score"])
            partner_hint = scored[:5]
        except Exception:
            pass

    return {"generations": gens, "target": target,
            "blue_order": [STAT_CN[k] for k in blue_order],
            "gaps": {STAT_CN[k]: v for k, v in gaps.items() if v > 0},
            "partner_hint": partner_hint}


def other_styles_snapshot(track: Track, inv: Inventory) -> List[Dict[str, object]]:
    """其他跑法的最佳候选速查。"""
    out = []
    for st in STYLE_SHORT:
        cands = rank_candidates(inv, track, st, top=1)
        if not cands:
            continue
        c = cands[0]
        out.append({"style": st, "full": STYLE_FULL[st],
                    "chara": c["chara"].name, "total": c["total"],
                    "distance": c["distance"], "surface": c["surface"],
                    "style_apt": c["style"]})
    out.sort(key=lambda x: -x["total"])
    return out


# ============================ 报告渲染 ============================

def render_report(result: Dict[str, object], inv: Inventory) -> str:
    t: Track = result["track"]
    style = result["style"]
    L = []
    A = L.append

    A("# 种马缺口规划报告")
    A("")
    A("## 一、目标赛道")
    A("")
    A("- **赛道**：%s" % t.label())
    A("- **跑法**：%s（%s）" % (STYLE_FULL[style], style))
    A("- 场地/马场修正：耐力 ×%.2f，力量 ×%.2f" % (t.cond[0], t.cond[1]))
    A("")

    A("## 二、主力马目标规格")
    A("")
    A("| 属性 | 目标值 | 自练基线（无继承） | 属性缺口 | 主要靠什么补 |")
    A("|---|---:|---:|---:|---|")
    base = {STAT_CN[k]: v for k, v in SELF_BASELINE.items()}
    for k in ("speed", "stamina", "power", "guts", "wisdom"):
        goal = result["stats_goal"][k]
        b = base[STAT_CN[k]]
        gap = max(0, goal - b)
        if gap <= 0:
            A("| %s | %d | %d | — | 已达标 |" % (STAT_CN[k], goal, b))
        else:
            how = "配卡训练为主，蓝因子辅助" if gap > 3 * BLUE_VALUE[3] else "蓝因子可直接补满"
            A("| %s | %d | %d | **%d** | %s |" % (STAT_CN[k], goal, b, gap, how))
    A("")
    A("**适性目标**：距离 %s / 场地 %s / 跑法 %s（距离 S 提升终盘速度，优先度最高）"
      % (result["apt_goal"]["距离"], result["apt_goal"]["场地"], result["apt_goal"]["跑法"]))
    A("")
    A("> 属性目标为社区经验估算（含常规回蓝技能），非精确模拟器结果；自练基线 = 无继承、中等偏上配卡可达值。")
    A("> **蓝因子上限**：初始继承固定给最大值，3 星 = +%d / 2 星 = +%d / 1 星 = +%d；"
      "理想 9 蓝配置下单属性 3 个 3 星 = **+%d**，缺口大于此值就必须靠配卡训练补。"
      % (BLUE_VALUE[3], BLUE_VALUE[2], BLUE_VALUE[1], 3 * BLUE_VALUE[3]))
    A("")

    A("## 三、候选主力马")
    A("")
    if not result["candidates"]:
        A("⚠ **库存为空** —— 请先填 `my_inventory/my_characters.csv`（在「拥有」列填 1）。")
        A("")
    for i, d in enumerate(result["candidates"], 1):
        c = d["score"]
        ch: Chara = c["chara"]
        A("### %d. %s —— %.1f 分" % (i, ch.card_name or ch.name, c["total"]))
        A("")
        A("- 形态：%s｜星级 %d｜觉醒 %d" % (ch.card_name, ch.star, ch.awakening))
        A("- 适性：距离 **%s** / 场地 %s / 跑法(%s) %s"
          % (c["distance"], c["surface"], STYLE_TO_APT[style], c["style"]))
        A("- 固有：%s" % c["uniq_note"])
        sk = c.get("skills") or {}
        if sk.get("unique"):
            A("- 本形态固有技能：%s" % "、".join(s.get("name", "") for s in sk["unique"]))
        if sk.get("awakening"):
            A("- 觉醒技能：%s" % "、".join(s.get("name", "") for s in sk["awakening"][:6]))
        if sk.get("initial"):
            A("- 初始技能（形态专属）：%s" % "、".join(s.get("name", "") for s in sk["initial"][:6]))
        A("- 成长率：%s" % ", ".join("%s %s" % (k, v) for k, v in c["growth"].items()))
        A("- 得分构成：%s" % "，".join("%s %.1f" % (k, v) for k, v in c["parts"].items()))
        A("")
        req = d["requirements"]
        A("**粉因子需求（适性改造）**")
        A("")
        A("| 项目 | 当前 | 目标 | 需阶段 | 需星数 | 说明 |")
        A("|---|---|---|---:|---:|---|")
        for k, v in req["pink"].items():
            A("| %s | %s | S | %d | %d | %s |"
              % (k, v.get("current", "—"), v["stages"], v["stars"], v["note"]))
        A("")
        if req["stat_gap"]:
            A("**属性缺口**：%s"
              % "，".join("%s +%d" % (k, v) for k, v in req["stat_gap"].items()))
            A("")
            A("  → 蓝因子目标优先序：%s（蓝因子只能补其中一小部分，其余靠配卡训练）"
              % " > ".join(req["blue_priority"]))
        else:
            A("**属性缺口**：无（自练基线已覆盖目标）")
        A("")
        A("**白因子关键技能**：%s" % "；".join(req["white"]))
        A("")
        if req["green"]:
            A("**推荐继承固有（绿因子）**：%s"
              % "；".join("%s(%s级·%s)" % (g["name"], g["tier"], g["cond"])
                         for g in req["green"][:5]))
        A("")
        deck = d["deck"]
        if deck.get("cards"):
            A("**配卡方案（%s 流）**：%s"
              % (deck["build"], "、".join(
                  "%s[%s/%s%s]" % (c.name, c.type, c.rarity,
                                   "·%d破" % c.limit if c.limit else "")
                  for c in deck["cards"])))
            if deck.get("missing"):
                A("")
                A("  ⚠ 缺卡：%s（用其他类型补齐或借好友）"
                  % "，".join("%s ×%d" % (k, v) for k, v in deck["missing"].items()))
        A("")

    A("## 四、现有种马供给 vs 缺口")
    A("")
    sup = result["supply"]
    if sup["count"] == 0:
        A("⚠ **没有任何成品种马记录** —— 按「从零规划」处理。")
        A("")
        A("| 因子 | 你现在有 | 理想配置 | 差距 |")
        A("|---|---|---|---|")
        A("| 蓝因子 | 0 | 9 蓝（单属性 3 个 3 星 = +%d 属性） | **缺全部** |"
          % result["ideal"]["blue_per_stat"])
        A("| 粉因子 | 0 | 单项 10 星（+4 阶段） | **缺全部** |")
        A("| 白因子 | 0 | 关键技能因子 + 剧本因子 + G1 比赛因子 | **缺全部** |")
        A("| 绿因子 | 0 | 高价值继承固有（S 级） | **缺全部** |")
    else:
        A("- 登记种马 %d 只" % sup["count"])
        A("- 蓝因子合计：%s" % ("，".join("%s +%d" % (k, v) for k, v in sup["blue"].items()) or "无"))
        A("- 粉因子合计：%s" % ("，".join("%s %d星" % (k, v) for k, v in sup["pink"].items()) or "无"))
        A("- 白因子技能：%s" % ("、".join(sup["white"]) or "无"))
        A("- 绿因子：%s" % ("、".join(sup["green"]) or "无"))
        A("- 跑过 G1：%s" % ("、".join(sup["g1"]) or "无"))
    A("")

    A("## 五、养成路线（还差多远 → 需要几代）")
    A("")
    bp = breeding_plan(inv, t, style, result)
    if bp.get("note"):
        A("⚠ %s" % bp["note"])
        A("")
    n_gen = len([g for g in bp.get("generations", [])
                  if g["role"] != "成品参赛马（目标马娘本人）"])
    if n_gen:
        A("需要 **%d 代**种马育成 + 1 代成品马（每代 = 一次完整育成）。"
          "顺序不可颠倒：后一代用前一代做种马。" % n_gen)
        A("")
        A("> ⚠ 赛程数由 route_planner 按「能跑就跑」生成，是**理论上限**："
          "不模拟体力 / 心情 / 落败，实战请按自己的配卡强度删减。")
        A("")
    for g in bp.get("generations", []):
        ch = g["chara"]
        A("### 第 %d 代 · %s —— %s" % (g["gen"], g["role"], ch.name))
        A("")
        if g.get("score"):
            s = g["score"]
            A("- 选型理由：主属性成长 %s%%｜本距离适性 %s｜历战广度 %d/4 档（综合 %.1f 分）"
              % (s["growth"], s["distance"], s["breadth"], s["total"]))
        else:
            A("- 这就是最终要上场的马，用前面几代做种马")
        st = g.get("stat_target") or {}
        if st:
            A("- 属性目标：%s"
              % "，".join("%s %s" % (k, v) for k, v in st.items()))
        A("- 说明：%s" % g["stat_note"])
        A("- 适性目标：%s" % g["apt_target"])
        sk = form_skills(ch)
        if sk.get("unique"):
            A("- 本形态固有技能：%s" % "、".join(s.get("name", "") for s in sk["unique"]))
        if sk.get("awakening"):
            A("- 觉醒技能：%s" % "、".join(s.get("name", "") for s in sk["awakening"][:6]))
        if sk.get("initial"):
            A("- 初始技能（形态专属）：%s" % "、".join(s.get("name", "") for s in sk["initial"][:6]))
        rt = g.get("route") or {}
        if rt:
            grades = rt.get("grades") or {}
            A("- 赛程（%s）：共 %d 场，G1 %d 场，期末粉丝 %s"
              % (g["route_mode"], rt.get("total", 0), grades.get("G1", 0),
                 rt.get("final_fans", 0)))
            if rt.get("g1_list"):
                # 跨年份同一场比赛会重复出现，去重后展示
                uniq_g1 = list(dict.fromkeys(rt["g1_list"]))
                A("  - G1 覆盖（去重 %d 场）：%s"
                  % (len(uniq_g1), "、".join(uniq_g1[:16])))
        else:
            A("- 赛程：%s" % g["route_mode"])
        if (g.get("deck") or {}).get("cards"):
            A("- 配卡（%s 流）：%s"
              % (g["deck"]["build"], "、".join(
                  "%s[%s/%s%s]" % (c.name, c.type, c.rarity,
                                   "·%d 破" % c.limit if c.limit else "")
                  for c in g["deck"]["cards"][:6])))
        if g.get("skills"):
            A("- 关键技能：%s" % "；".join(str(s) for s in g["skills"][:3]))
        A("- **产出**：%s" % g["output"])
        if g.get("affinity"):
            A("- 与目标马相性：%d 分（%s，%s）"
              % (g["affinity"]["score"], g["affinity"]["grade"],
                 g["affinity"]["note"]))
        A("")
    if bp.get("partner_hint"):
        A("### 高相性种马候选（与目标马的固定相性分）")
        A("")
        A("| 角色 | 相性分 | 等级 |")
        A("|---|---:|:--:|")
        for p in bp["partner_hint"]:
            A("| %s | %d | %s |" % (p["name"], p["score"], p["grade"]))
        A("")
        A("> 相性分 ≥151 双圈（⌾） / 51~150 单圈（〇） / <51 三角（△）。相性越高，第二、三次继承触发概率越高。")
        A(">")
        A("> ⚠ **固定相性分普遍偏低**（多数角色组合 <51，都是 △）—— 这是正常的。"
          "真正拉开差距的是**胜鞍分**：种马与祖辈跑过相同比赛（每重合一场 +1pt，金章组合另计）。"
          "所以历战代不是可选项，是相性分的主要来源 —— 借好友种马时也要挑赛程重合度高的。")
        A("")
    gm = gold_medal_hint()
    if gm:
        A("### 金章组合（对齐胜鞍可加相性分）")
        A("")
        for g in gm[:12]:
            A(g if str(g).startswith("-") else "- %s" % g)
        A("")

    A("## 六、下一步")
    A("")
    A("1. 填 `my_inventory/my_characters.csv`（拥有列填 1，星级/觉醒等级可选）")
    A("2. 填 `my_inventory/my_support_cards.csv`（拥有列填 1，突破数建议填）")
    A("3. 重跑本工具，即可得到针对你库存的候选排名与配卡方案")
    A("4. 每练出一只种马，往 `my_studs.csv` 补一行，缺口会逐代收敛")
    A("")
    return "\n".join(L)


def print_summary(result: Dict[str, object], inv: Inventory, top: int = 5) -> None:
    t: Track = result["track"]
    style = result["style"]
    print("")
    print("=" * 68)
    print(" 种马缺口规划 · %s" % t.label())
    print(" 跑法：%s" % STYLE_FULL[style])
    print("=" * 68)
    print("")
    print("【主力马目标】")
    print("  " + "  ".join("%s %d" % (STAT_CN[k], result["stats_goal"][k])
                            for k in ("speed", "stamina", "power", "guts", "wisdom")))
    print("  适性目标：距离 S / 场地 S / 跑法 S")
    print("")
    if not result["candidates"]:
        print("【候选马娘】库存为空，请先填 my_inventory/my_characters.csv")
        print("")
    else:
        print("【候选主力马 Top %d】" % len(result["candidates"]))
        for i, d in enumerate(result["candidates"], 1):
            c = d["score"]
            ch: Chara = c["chara"]
            print("  %d. %-28s %5.1f 分   距离%s 场地%s 跑法%s"
                  % (i, ch.name, c["total"], c["distance"], c["surface"], c["style"]))
        print("")
        best = result["candidates"][0]
        req = best["requirements"]
        print("【最优候选缺口】%s" % best["score"]["chara"].name)
        for k, v in req["pink"].items():
            print("  粉·%-12s 需 %d 阶段 / %d 星 → %s"
                  % (k, v["stages"], v["stars"], v["note"]))
        if req["stat_gap"]:
            print("  属性缺口·%s" % "，".join("%s +%d" % (k, v) for k, v in req["stat_gap"].items()))
            print("  蓝因子优先序·%s（单属性 3 个 3 星 = +%d，缺口更大只能靠配卡训练）"
                  % (" > ".join(req["blue_priority"]), 3 * BLUE_VALUE[3]))
        else:
            print("  属性缺口·无")
        print("  白·%s" % ("；".join(str(x) for x in req["white"][:2]) or "—"))
        print("")
    print("【养成计划】")
    bp = breeding_plan(inv, t, style, result)
    if bp.get("note"):
        print("  ⚠ %s" % bp["note"])
    for g in bp.get("generations", []):
        rt = g.get("route") or {}
        extra = ""
        if rt:
            extra = "（赛程 %d 场 / G1 %d 场）" % (
                rt.get("total", 0), (rt.get("grades") or {}).get("G1", 0))
        aff = ""
        if g.get("affinity"):
            aff = " 相性%d%s" % (g["affinity"]["score"], g["affinity"]["grade"])
        print("  第%d代 %-12s %s%s%s" % (g["gen"], g["focus"], g["chara"].name, extra, aff))
        print("        → %s" % g["output"])
    if bp.get("partner_hint"):
        print("  高相性种马候选：%s" % "，".join(
            "%s %d分" % (p["name"], p["score"]) for p in bp["partner_hint"][:3]))
    print("")
    sup = result["supply"]
    if sup["count"] == 0:
        print("【现有种马】无 —— 按从零规划，需要走完整 %d 代流水线" % 5)
    else:
        print("【现有种马】%d 只" % sup["count"])
        print("  蓝：%s" % ("，".join("%s +%d" % (k, v) for k, v in sup["blue"].items()) or "无"))
        print("  粉：%s" % ("，".join("%s %d星" % (k, v) for k, v in sup["pink"].items()) or "无"))
    print("")
    print("完整报告见 my_inventory/stud_plan_report.md")
    print("")


# ============================ CLI ============================

def _track_from_race(name: str) -> Optional[Track]:
    """按比赛名从 race_bwiki 反查赛道。"""
    try:
        races = load_json("race_bwiki.json")["races"]
        for r in races:
            if r.get("name") == name or name in (r.get("jp_name") or ""):
                return Track(venue=r.get("venue", ""), distance=int(r.get("distance") or 0),
                             surface=r.get("track", "草地"), direction=r.get("direction", "右"),
                             name=r.get("name", ""))
    except Exception:
        pass
    return None


def _main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="种马缺口规划器")
    ap.add_argument("--race", help="按比赛名查赛道，如 中山大奖赛")
    ap.add_argument("--venue", default="", help="场地，如 中山")
    ap.add_argument("--distance", type=int, default=2000, help="距离(米)")
    ap.add_argument("--track", dest="surface", default="草地", help="草地/泥地")
    ap.add_argument("--direction", default="右", help="左/右")
    ap.add_argument("--weather", default="晴")
    ap.add_argument("--condition", default="良", help="良/稍重/重/不良")
    ap.add_argument("--style", default="差", help="逃/先/差/追")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--inventory", default=DEFAULT_INVENTORY, help="库存目录")
    ap.add_argument("--out", default="", help="报告输出路径")
    ap.add_argument("--inventory-check", action="store_true", help="只检查库存填报情况")
    args = ap.parse_args(argv)

    inv = load_inventory(args.inventory)
    if args.inventory_check:
        print("库存目录：%s" % args.inventory)
        print("  马娘：%d 只" % len(inv.characters))
        print("  协助卡：%d 张" % len(inv.cards))
        print("  成品种马：%d 只" % len(inv.studs))
        if inv.empty:
            print("  ⚠ 库存为空，请先填模板：python tools/gen_inventory_template.py")
        return 0

    if args.race:
        t = _track_from_race(args.race)
        if t is None:
            print("[错误] 未找到比赛：%s" % args.race, file=sys.stderr)
            return 2
    else:
        t = Track(venue=args.venue, distance=args.distance, surface=args.surface,
                  direction=args.direction, weather=args.weather,
                  condition=args.condition)

    style = STYLE_ALIAS.get(args.style, args.style)
    if style not in STYLE_SHORT:
        print("[错误] 跑法只支持 %s" % (STYLE_SHORT,), file=sys.stderr)
        return 2

    result = plan(t, inv, style=style, top=args.top)
    print_summary(result, inv, top=args.top)

    out = args.out or os.path.join(args.inventory, "stud_plan_report.md")
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(render_report(result, inv))
        print("报告已写入：%s" % out)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print("[警告] 报告写入失败：%s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
