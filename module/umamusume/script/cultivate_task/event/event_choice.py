"""event_choice.py — 育成事件「选哪个选项」的智能决策（P2 事件识别接入）。

背景
----
原 manifest.get_event_choice 只覆盖硬编码的少数事件（新年/青春杯队名等），
其余一律默认选项 1。事件库 event_db.json（5165 条，含国服简中名 + 每个选项的
结构化日文效果 effects）已就绪，这里实现「命中库 → 按育成上下文给每个选项打分」。

决策链（由 manifest.get_event_choice 调用）
------------------------------------------------
1. scenario_event.py 既有硬编码事件优先（人工规则：新年按体力、青春杯按队名配置）
2. 事件库命中（event_db.search_by_name）→ event_choice.score_event_choices(ctx, event)
   按「当前属性缺口 + 技能点 + 技能提示命中想学技能 + 干劲/体力」给每个选项打分
3. 未命中 / 无效果数据 / 全部 0 分 → 返回默认选项 1

效果串解析
----------
每个 choice.effects 是日文效果串列表，形如：
    'スピード(速度)+20'            → 属性
    'スキルPt(技能点数)+10'        → 技能点
    '賢さ(智力)+10~20'             → 区间
    'やる気(干劲)アップ(提升)'      → 干劲
    '『勢い任せ』のヒントLv+1'      → 技能提示
    'ランダムで(有概率)『練習上手◯』になる' → 随机
    '根性(毅力)+20' ...
解析器把这些串折叠成若干「收益 token」，再由打分器按 ctx 当前缺口加权。
"""

import re

try:
    import bot.base.log as logger
    log = logger.get_logger(__name__)
except Exception:                      # 无 colorlog/bot 环境（单测）时用静默兜底
    import logging
    log = logging.getLogger(__name__)
    log.addHandler(logging.NullHandler())

# 效果串里的五维属性关键词 → 标准字段名（与 types.UmaAttribute 顺序一致）
ATTR_CN = {
    "スピード": "speed",
    "スタミナ": "stamina",
    "パワー": "power",
    "根性": "guts",
    "賢さ": "wisdom",
}

# 反向：给日志/调试用
ATTR_LABEL = {v: k for k, v in ATTR_CN.items()}

# 五维在 expect_attribute / uma_attribute 里的下标顺序（types.UmaAttribute 字段序）
ATTR_ORDER = ("speed", "stamina", "power", "guts", "wisdom")

# 效果串中括号里的简中对照（如 スピード(速度)），提取时也做候选
_CN_IN_PAREN = {
    "速度": "speed", "耐力": "stamina", "力量": "power",
    "毅力": "guts", "智力": "wisdom", "根性": "guts",
    "能力": "random_attr",
}

_RE_ATTR = re.compile(r"(スピード|スタミナ|パワー|根性|賢さ|"
                      r"速度|耐力|力量|毅力|智力)")
# 区间形如 +10~20 / +10〜20 / +5-10；sign 允许全角 −。四组: s1 lo s2 hi
_RE_ATTR_NUM = re.compile(r"([+\-−])\s*(\d+)\s*(?:~|〜|[-−])\s*([+\-−]?)\s*(\d+)")
_RE_NUM = re.compile(r"([+\-−])\s*(\d+)")
_RE_SKILL_PT = re.compile(r"スキルPt\(技能点数\)")
_RE_HINT = re.compile(r"『([^』]+)』のヒントLv")
_RE_MOTIV = re.compile(r"やる気\(干劲\)(アップ|ダウン|3段階ダウン|2段階ダウン)")
_RE_STAMINA = re.compile(r"体力([+\-−]?\s*\d+)")
_RE_GUAGE = re.compile(r"絆ゲージ([+\-−]?\s*\d+)")
_RE_RANDOM_ATTR = re.compile(r"5種ステータス\(能力\)からランダムに\(随机\)(\d*)種")
_RE_BADGE = re.compile(r"スキルヒント|ヒント")


class ChoiceScore(object):
    """一次选项打分的可读结果。"""

    __slots__ = ("index", "total", "parts", "text")

    def __init__(self, index, total, parts, text):
        self.index = index          # 1-based 选项序号
        self.total = total          # 总分（浮点）
        self.parts = parts          # [(说明, 分值)] 供日志
        self.text = text            # 选项原文

    def __repr__(self):
        return "<Choice #%d total=%.1f %s>" % (self.index, self.total, self.text)


# ---------------------------------------------------------------- 效果解析


def _to_number(sign, num_str):
    """'+10' -> 10, '-5' -> -5；日文全角减号 − 一并处理。"""
    v = int(num_str)
    return -v if sign in ("-", "−") else v


def parse_effect(effect: str):
    """解析单条效果串 → [(key, value, note)]。

    key 取值：speed/stamina/power/guts/wisdom | skill_pt | hint | motivation |
              stamina(体力) | gauge(羁绊) | random_attr | unknown
    value：数值收益（motivation/gauge 等以固定约定值近似）或 0。
    """
    if not effect:
        return []
    out = []
    txt = effect.strip()

    # 1) 技能提示（要最先查：技能名里可能含属性词）
    m = _RE_HINT.search(txt)
    if m:
        lv = 0
        mn = _RE_NUM.search(txt)
        if mn:
            lv = _to_number(mn.group(1), mn.group(2))
        elif _RE_NUM.search(txt.replace("Lv", "")):
            mn = _RE_NUM.search(txt.replace("Lv", ""))
            lv = _to_number(mn.group(1), mn.group(2))
        out.append(("hint", lv, "技能提示『%s』Lv%+d" % (m.group(1), lv)))
        # 一条提示就返回；hint 描述里不叠加其它词义
        return out

    # 2) 技能点
    if _RE_SKILL_PT.search(txt):
        mn = _RE_NUM.search(txt)
        v = _to_number(mn.group(1), mn.group(2)) if mn else 0
        out.append(("skill_pt", v, "技能点 %+d" % v))
        return out

    # 3) 体力
    m = _RE_STAMINA.search(txt)
    if m:
        mm = _RE_NUM.search(m.group(1))
        if mm:
            v = _to_number(mm.group(1), mm.group(2))
            out.append(("stamina", v, "体力 %+d" % v))
            return out

    # 4) 属性（含区间 10~20 与单值 +20）
    #    随机属性串（5種ステータス…ランダム…種を+5~10）不含具体属性词，
    #    需在 _RE_ATTR 前单独识别
    if "ステータス" in txt and "ランダム" in txt and _RE_RANDOM_ATTR.search(txt):
        span = _RE_ATTR_NUM.search(txt)
        if span:
            lo = _to_number(span.group(1), span.group(2))
            hi = _to_number(span.group(3) or "+", span.group(4))
            v = (lo + hi) / 2.0
        else:
            mn = _RE_NUM.search(txt)
            v = _to_number(mn.group(1), mn.group(2)) if mn else 0
        if v:
            out.append(("random_attr", v, "随机属性≈%+.0f" % v))
            return out
        out.append(("random_attr", 0, "随机属性(未知幅度)"))
        return out

    am = _RE_ATTR.search(txt)
    if am:
        key = ATTR_CN.get(am.group(1))
        # 命中 (速度) 这种括号简中对照但日文未命中的情况
        if key is None:
            for cn, k in _CN_IN_PAREN.items():
                if cn in txt:
                    key = k
                    break
        if key == "random_attr":
            # 随机属性：以区间中值近似（保守：按 1 项随机给期望）
            span = _RE_ATTR_NUM.search(txt)
            if span:
                lo = _to_number(span.group(1), span.group(2))
                hi = _to_number(span.group(3) or "+", span.group(4))
                v = (lo + hi) / 2.0
            else:
                mn = _RE_NUM.search(txt)
                v = _to_number(mn.group(1), mn.group(2)) if mn else 0
            if v:
                out.append(("random_attr", v, "随机属性≈%+.0f" % v))
                return out
            out.append(("random_attr", 0, "随机属性(未知幅度)"))
            return out
        if key:
            # 区间 10~20 / 10~20：中值近似；单值 +20
            span = _RE_ATTR_NUM.search(txt)
            if span:
                lo = _to_number(span.group(1), span.group(2))
                hi = _to_number(span.group(3) or "+", span.group(4))
                v = (lo + hi) / 2.0
            else:
                mn = _RE_NUM.search(txt)
                v = _to_number(mn.group(1), mn.group(2)) if mn else 0
            out.append((key, v, "%s %+g" % (key, v)))
            return out

    # 5) 干劲
    m = _RE_MOTIV.search(txt)
    if m:
        s = m.group(1)
        if s.startswith("アップ"):
            v = 1
        else:
            # ダウン / 2段階 / 3段階
            lv = _RE_NUM.search(s) or _RE_NUM.search(txt)
            v = -1
            if "3段階" in txt:
                v = -3
            elif "2段階" in txt:
                v = -2
        out.append(("motivation", v, "干劲 %+d 段" % v))
        return out

    # 6) 羁绊
    m = _RE_GUAGE.search(txt)
    if m:
        mm = _RE_NUM.search(m.group(1))
        v = _to_number(mm.group(1), mm.group(2)) if mm else 0
        out.append(("gauge", v, "羁绊 %+d" % v))
        return out

    # 7) 负面/异常词（无数值的坏结果）
    neg = ("ダウン", "やる気", "練習下手", "練習ベタ", "バ場状況が悪化")
    if any(w in txt for w in neg):
        out.append(("unknown", 0, "负面/未知: %s" % txt[:24]))
        return out

    out.append(("unknown", 0, "未解析: %s" % txt[:24]))
    return out


def parse_effects(effects):
    """解析整个选项的 effects 列表 → 合并后的 [(key, total_value)]。"""
    merged = {}
    details = []
    for fx in effects or []:
        for key, v, note in parse_effect(fx):
            merged[key] = merged.get(key, 0) + v
            details.append(note)
    return merged, details


# ---------------------------------------------------------------- 打分


def _attr_gap_weight(ctx, key):
    """当前属性缺口权重：目标 - 现状（缺失越大越值钱），无 ctx 时退化为均权。

    返回 0~3 的权重：缺口 ≥600 → 3, ≥300 → 2, >0 → 1, 达标/溢出 → 0.3。
    """
    try:
        detail = ctx.cultivate_detail
        goal = detail.expect_attribute
        uma = detail.turn_info.uma_attribute
        if not goal or not uma:
            return 1.0
        idx = ATTR_ORDER.index(key)
        g = goal[idx]
        cur = getattr(uma, key, 0)
        gap = max(0, g - cur)
        if gap >= 600:
            return 3.0
        if gap >= 300:
            return 2.0
        if gap > 0:
            return 1.0
        return 0.3
    except Exception:
        return 1.0


def _skill_pt_weight(ctx):
    """技能点权重：早期(日期<36)相对低，后期攒技能点打比赛价值升高。"""
    try:
        date = ctx.cultivate_detail.turn_info.date
    except Exception:
        date = 0
    if date <= 0:
        return 1.0
    return 1.2 if date > 48 else 1.0


def _want_hint(ctx, skill_name):
    """技能提示『skill_name』是否命中用户想学的技能（learn_skill_list 展平）。"""
    if not skill_name or not ctx:
        return False
    try:
        wanted = []
        for group in (ctx.cultivate_detail.learn_skill_list or []):
            for s in group:
                if s:
                    wanted.append(s)
        return skill_name in wanted
    except Exception:
        return False


def score_choice(ctx, choice, index):
    """给单个事件选项打分 → ChoiceScore。

    打分口径（经验值，供打磨）：
      * 属性：+value × 缺口权重
      * 技能点：+value × 技能点权重
      * 技能提示：命中想学技能 +120，否则 +25
      * 干劲：+1 段 = +60，-1 段 = -80
      * 体力：每点 -0.3（体力是资源，选项里直接扣体力不划算但非致命）
      * 羁绊：+8/点（影响后续事件概率，价值低）
    """
    merged, details = parse_effects(choice.get("effects") or [])
    total = 0.0
    parts = []
    for key, v in merged.items():
        if key in ATTR_ORDER:
            w = _attr_gap_weight(ctx, key)
            s = v * w
            parts.append(("属性%s(%+g)×%.1f" % (key, v, w), s))
        elif key == "skill_pt":
            w = _skill_pt_weight(ctx)
            s = v * w
            parts.append(("技能点%+d×%.1f" % (v, w), s))
        elif key == "hint":
            # hint 解析结果 value=等级，但加分按技能价值而非等级
            s = 120.0 if _want_hint(ctx, "") else 25.0
            # 上面拿不到技能名，重跑一次解析取名字
            for fx in (choice.get("effects") or []):
                m = _RE_HINT.search(fx)
                if m and _want_hint(ctx, m.group(1)):
                    s = 120.0
                    break
            parts.append(("技能提示", s))
        elif key == "motivation":
            s = 60.0 * v if v > 0 else 80.0 * v
            parts.append(("干劲%+d段" % v, s))
        elif key == "stamina":
            s = -0.3 * v if v < 0 else 0.0  # 只惩罚扣体力，加体力不额外奖励
            parts.append(("体力%+d" % v, s))
        elif key == "gauge":
            s = 8.0 * max(0, v)
            parts.append(("羁绊%+d" % v, s))
        elif key == "random_attr":
            # 随机属性：中值 × 五维平均缺口权重（不知道会加哪个，取均值）
            w_avg = sum(_attr_gap_weight(ctx, k) for k in ATTR_ORDER) / len(ATTR_ORDER)
            s = v * w_avg
            parts.append(("随机属性%+g×%.1f" % (v, w_avg), s))
        else:
            s = 0.0
            parts.append(("其他", 0.0))
        total += s
    return ChoiceScore(index, round(total, 2), parts,
                       (choice.get("text") or "")[:20])


def pick_best_choice(ctx, event):
    """给一条事件记录（event_db 的 dict）打分并返回最优选项序号（1-based）。

    无选项/无效果数据/最高分 ≤0 → 返回 1（默认）。
    """
    choices = event.get("choices") or []
    if not choices:
        return 1
    scored = []
    for i, c in enumerate(choices, 1):
        cs = score_choice(ctx, c, i)
        scored.append(cs)
        if cs.parts:
            log.debug("  选项%d[%s]: %.1f分 (%s)",
                      cs.index, cs.text, cs.total,
                      "; ".join("%s%.1f" % (n, s) for n, s in cs.parts))
    best = max(scored, key=lambda x: x.total)
    if best.total <= 0:
        log.debug("事件[%s] 无正向收益选项，默认选1", (event.get("name") or "")[:20])
        return 1
    return best.index
