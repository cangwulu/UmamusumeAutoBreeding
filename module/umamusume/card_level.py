# -*- coding: utf-8 -*-
"""协助卡「等级上限」规则 —— 全项目**唯一数据源**。

游戏规则（国服现行，已交叉验证）：
    等级上限 = 稀有度基准 + 5 × 突破数（突破数 0~4）

    稀有度   0破  1破  2破  3破  4破
    SSR      30   35   40   45   50
    SR       25   30   35   40   45
    R        20   25   30   35   40

消费方（一律从这里取，禁止各自写死数值，避免前后端规则漂移）：
  * module/umamusume/asset/stud_planner.py   读库存 CSV 时按上限钳制等级 / 判断「已练满」
  * module/umamusume/planning/inventory.py   POST /api/inventory 保存时校验并钳制
  * module/umamusume/planning/web_api.py     规则随 GET /api/inventory 下发给前端
  * public/planning.html                     等级下拉按「稀有度 + 突破数」联动（只信下发的规则）
  * tools/gen_inventory_template.py          CSV 表头文案（等级列名不再写死 1-50）
  * tools/gen_example_with_forms.py          同上

稀有度缺失/未知时统一按 SSR 降级（等价于「给足 1-50 的空间」），绝不抛异常。
"""

# ---------------- 规则常量 ----------------

#: 稀有度 -> 0 突破时的等级上限基准
RARITY_BASE_LEVEL = {"SSR": 30, "SR": 25, "R": 20}

#: 稀有度未知时的兜底稀有度（按 SSR 处理，即 1-50 的空间）
DEFAULT_RARITY = "SSR"

#: 已知稀有度（用于前端下拉/说明文案的顺序）
KNOWN_RARITIES = ("SSR", "SR", "R")

#: 每 1 点突破数提升的等级上限
LEVEL_PER_AWAKEN = 5

#: 突破数取值区间
MIN_AWAKEN = 0
MAX_AWAKEN = 4

#: 等级下界（等级是 1 起，不是 0）
MIN_LEVEL = 1

# ---------------- CSV 表头兼容 ----------------
# 旧模板写的是「等级(1-50)」这个静态描述，与稀有度/突破无关，已改为「等级(1-上限)」。
# 读取时按候选顺序匹配（精确优先，再子串兜底），保证老 CSV 不失效。

#: 等级列候选表头（新 -> 旧 -> 兜底）
LEVEL_HEADERS = ("等级(1-上限)", "等级(1-50)", "等级")

#: 突破列候选表头
AWAKEN_HEADERS = ("突破数(0-4)", "突破数", "突破")

#: 当前（新）表头文案，模板生成器用
LEVEL_HEADER = LEVEL_HEADERS[0]
AWAKEN_HEADER = AWAKEN_HEADERS[0]


def normalize_rarity(rarity) -> str:
    """把任意写法的稀有度归一化成 SSR / SR / R。

    未知或缺失时返回 DEFAULT_RARITY（按 SSR 降级），保证调用方永远拿得到基准。

    >>> normalize_rarity(" ssr ") == "SSR"
    True
    >>> normalize_rarity("") == "SSR"
    True
    >>> normalize_rarity(None) == "SSR"
    True
    >>> normalize_rarity("UR") == "SSR"
    True
    """
    key = str(rarity if rarity is not None else "").strip().upper()
    if key in RARITY_BASE_LEVEL:
        return key
    # 容错：全角/空格/标点干扰，如 "ＳＳＲ" "S S R" "SSR。"
    compact = "".join(ch for ch in key if ch.isalnum())
    if compact in RARITY_BASE_LEVEL:
        return compact
    return DEFAULT_RARITY


def is_known_rarity(rarity) -> bool:
    """稀有度是否是已知的 SSR / SR / R（未知时前端可提示降级）。"""
    return str(rarity if rarity is not None else "").strip().upper() in RARITY_BASE_LEVEL


def normalize_awaken(awaken) -> int:
    """突破数归一到 [MIN_AWAKEN, MAX_AWAKEN]；不可解析时按 0 处理。"""
    try:
        n = int(float(str(awaken if awaken is not None else "").strip()))
    except (TypeError, ValueError):
        return MIN_AWAKEN
    return max(MIN_AWAKEN, min(MAX_AWAKEN, n))


def level_cap(rarity, awaken=0) -> int:
    """等级上限 = 稀有度基准 + LEVEL_PER_AWAKEN × 突破数。

    >>> level_cap("SSR", 0), level_cap("SSR", 4)
    (30, 50)
    >>> level_cap("SR", 0), level_cap("SR", 4)
    (25, 45)
    >>> level_cap("R", 0), level_cap("R", 4)
    (20, 40)
    >>> level_cap(None, 2)      # 稀有度缺失 -> 按 SSR
    40
    """
    base = RARITY_BASE_LEVEL[normalize_rarity(rarity)]
    return base + LEVEL_PER_AWAKEN * normalize_awaken(awaken)


def max_level_cap(rarity) -> int:
    """该稀有度在满突破时的等级上限（即「练满」的目标等级）。"""
    return level_cap(rarity, MAX_AWAKEN)


def clamp_level(level, rarity, awaken=0) -> int:
    """把等级钳制到 [MIN_LEVEL, level_cap(rarity, awaken)]。

    不可解析（空串/None/脏数据）时返回上限（等价于「按满级算」，与旧 UI 默认一致）。
    """
    cap = level_cap(rarity, awaken)
    try:
        n = int(float(str(level if level is not None else "").strip()))
    except (TypeError, ValueError):
        return cap
    if n <= 0:
        return cap
    return max(MIN_LEVEL, min(cap, n))


def rules_payload() -> dict:
    """给前端的规则快照（GET /api/inventory 的 card_level_rules 字段）。

    前端只做「基准 + per_awaken × 突破数」这一层算术，数值全部来自这里。
    """
    return {
        "base": dict(RARITY_BASE_LEVEL),
        "per_awaken": LEVEL_PER_AWAKEN,
        "min_level": MIN_LEVEL,
        "min_awaken": MIN_AWAKEN,
        "max_awaken": MAX_AWAKEN,
        "default_rarity": DEFAULT_RARITY,
        "rarity_order": list(KNOWN_RARITIES),
    }


def pick_cell(row, candidates, default=""):
    """从 csv.DictReader 的行里按候选列名取值（精确优先，再子串匹配）。

    用于兼容新旧表头：老 CSV 写「等级(1-50)」，新模板写「等级(1-上限)」。
    命中但值为空时继续找下一个候选（例如用户两列都留了）。

    :param row: csv.DictReader 的一行（dict）
    :param candidates: 候选列名元组，优先级从高到低
    :param default: 全部未命中时的返回值
    """
    if not row:
        return default
    keys = [k for k in row.keys() if k]
    for name in candidates:
        for key in keys:
            if key == name:
                val = row.get(key)
                if str(val if val is not None else "").strip() != "":
                    return val
    for name in candidates:
        for key in keys:
            if name in key:
                val = row.get(key)
                if str(val if val is not None else "").strip() != "":
                    return val
    return default
