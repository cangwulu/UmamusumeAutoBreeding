# -*- coding: utf-8 -*-
"""InventoryService: 库存加载与校验 (my_inventory/*.csv).

薄包装 asset/stud_planner.load_inventory —— 打分/缺口算法全部复用，
本层只负责「用户侧」的检查与友好输出。
"""

import os
import sys
from typing import Dict, Optional

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_PKG_DIR)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from module.umamusume import card_level
except Exception as exc:  # pragma: no cover - card_level 只依赖标准库, 理论上不会失败
    card_level = None
    _CARD_LEVEL_ERR = exc
else:
    _CARD_LEVEL_ERR = None

try:
    from module.umamusume.asset import stud_planner
except Exception as exc:  # pragma: no cover
    stud_planner = None
    _IMPORT_ERR = exc
else:
    _IMPORT_ERR = None

DEFAULT_INVENTORY = os.path.join(_PROJECT_ROOT, "my_inventory")
REQUIRED_FILES = ("my_characters.csv", "my_support_cards.csv", "my_studs.csv")


def ensure_import():
    if stud_planner is None:
        raise RuntimeError("无法导入 asset/stud_planner: %r" % (_IMPORT_ERR,))


def load(directory: str = DEFAULT_INVENTORY):
    """加载 Inventory（底层由 stud_planner.load_inventory 完成）。"""
    ensure_import()
    return stud_planner.load_inventory(directory)


def check(directory: str = DEFAULT_INVENTORY) -> Dict[str, object]:
    """库存体检: 返回统计与问题清单（供 CLI/未来 Web 复用）。"""
    ensure_import()
    inv = stud_planner.load_inventory(directory)
    missing = [f for f in REQUIRED_FILES
               if not os.path.isfile(os.path.join(directory, f))]
    problems = []
    if missing:
        problems.append("缺少模板文件: %s（先跑 python tools/gen_inventory_template.py）" % ", ".join(missing))
    if inv.empty:
        problems.append("库存为空: 请按模板填写 拥有/星级/觉醒 列")
    # 拥有列未标注(全部空白)是最常见的半填状态 —— 由底层 empty/统计辅助判断
    return {
        "directory": directory,
        "characters": len(inv.characters),
        "cards": len(inv.cards),
        "studs": len(inv.studs),
        "empty": inv.empty,
        "missing_files": missing,
        "problems": problems,
    }


# ============ CSV 行级读写（Web 点选页用, 保留用户备注等其它列） ============

CHAR_HEADER = ["形态名", "角色名", "拥有", "星级", "觉醒", "备注"]  # 拥有的确切表头前缀
CARD_HEADER = ["卡名", "关联马娘", "类型", "稀有度", "拥有", "突破", "等级", "备注"]


def _read_csv_rows(path: str) -> list:
    """读回原始行(list[list]), 处理 BOM。"""
    import csv
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def _write_csv_rows(path: str, rows: list) -> None:
    import csv
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)


def read_state(directory: str = DEFAULT_INVENTORY) -> Dict[str, object]:
    """读库存三表为 JSON 友好结构(供网页渲染), 每项附图片文件名(img 可为空)。"""
    rows = _read_csv_rows(os.path.join(directory, "my_characters.csv"))
    header = rows[0] if rows else []
    # 定位列（按表头名, 容错顺序）
    def col(name, default):
        for i, h in enumerate(header):
            if name in h:
                return i
        return default
    ci_form, ci_role = col("形态名", 0), col("角色名", 1)
    ci_own, ci_star, ci_awk = col("拥有", 2), col("星级", 3), col("觉醒", 4)
    ci_note = col("备注", 5)
    characters = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        characters.append({
            "idx": len(characters), "form": r[ci_form].strip(),
            "role": r[ci_role].strip(),
            "own": (r[ci_own].strip() if len(r) > ci_own else "") == "1",
            "star": _clean_int(r, ci_star), "awaken": _clean_int(r, ci_awk),
            "note": (r[ci_note].strip() if len(r) > ci_note else ""),
        })

    rows = _read_csv_rows(os.path.join(directory, "my_support_cards.csv"))
    header = rows[0] if rows else []
    def col2(name, default):
        for i, h in enumerate(header):
            if name in h:
                return i
        return default
    k_name, k_role = col2("卡名", 0), col2("关联马娘", 1)
    k_type, k_rar = col2("类型", 2), col2("稀有度", 3)
    k_own, k_awk, k_lv = col2("拥有", 4), col2("突破", 5), col2("等级", 6)
    cards = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        cards.append({
            "idx": len(cards), "name": r[k_name].strip(),
            "role": (r[k_role].strip() if len(r) > k_role else ""),
            "ctype": (r[k_type].strip() if len(r) > k_type else ""),
            "rarity": (r[k_rar].strip() if len(r) > k_rar else ""),
            "own": (r[k_own].strip() if len(r) > k_own else "") == "1",
            "awaken": _clean_int(r, k_awk), "level": _clean_int(r, k_lv),
        })

    return {"characters": characters, "cards": cards}


def apply_updates(char_updates: list, card_updates: list,
                  directory: str = DEFAULT_INVENTORY) -> Dict[str, int]:
    """按 idx 更新 拥有/星级/觉醒(马娘) 与 拥有/突破/等级(卡)。

    只改指定列, 其余(备注/角色名等)原样保留。
    """
    n = {"characters": 0, "cards": 0, "clamped": 0}
    if char_updates:
        rows = _read_csv_rows(os.path.join(directory, "my_characters.csv"))
        header = rows[0] if rows else []
        ci_own, ci_star, ci_awk = 2, 3, 4
        for i, h in enumerate(header):
            if "拥有" in h:
                ci_own = i
            elif "星级" in h:
                ci_star = i
            elif "觉醒" in h:
                ci_awk = i
        for u in char_updates:
            idx = int(u.get("idx", -1))
            row_idx = idx + 1  # 跳过表头
            if 0 <= idx < len(rows) - 1:
                r = rows[row_idx]
                while len(r) <= max(ci_own, ci_star, ci_awk):
                    r.append("")
                r[ci_own] = "1" if u.get("own") else ""
                r[ci_star] = str(u.get("star", "")) if u.get("own") else ""
                r[ci_awk] = str(u.get("awaken", "")) if u.get("own") else ""
                n["characters"] += 1
        _write_csv_rows(os.path.join(directory, "my_characters.csv"), rows)

    if card_updates:
        rows = _read_csv_rows(os.path.join(directory, "my_support_cards.csv"))
        header = rows[0] if rows else []
        k_own, k_awk, k_lv, k_rar = 4, 5, 6, 3
        for i, h in enumerate(header):
            if "拥有" in h:
                k_own = i
            elif "突破" in h:
                k_awk = i
            elif "等级" in h:
                k_lv = i
            elif "稀有度" in h:
                k_rar = i
        for u in card_updates:
            idx = int(u.get("idx", -1))
            if 0 <= idx < len(rows) - 1:
                r = rows[idx + 1]
                while len(r) <= max(k_own, k_awk, k_lv, k_rar):
                    r.append("")
                own = bool(u.get("own"))
                rarity = (r[k_rar].strip() if len(r) > k_rar else "")
                raw_awk = u.get("awaken", 0)
                raw_lv = u.get("level", 0)
                awk = _norm_awaken(raw_awk)
                lv = _clamp_level(raw_lv, rarity, awk)
                if own and (_as_int(raw_awk) != awk or _as_int(raw_lv) != lv):
                    n["clamped"] += 1
                r[k_own] = "1" if own else ""
                r[k_awk] = str(awk) if own else ""
                r[k_lv] = str(lv) if own else ""
                n["cards"] += 1
        _write_csv_rows(os.path.join(directory, "my_support_cards.csv"), rows)
    return n


# ---------------- 种马登记（成品种马 my_studs.csv，行少→全量替换） ----------------

STUD_HEADERS = ["种马角色名", "速度", "耐力", "力量", "根性", "智力",
                "蓝因子(如:速度3星,耐力2星)", "粉因子(如:中距离3星)",
                "白因子技能(逗号分隔)", "绿因子(继承固有)", "跑过的G1(逗号分隔)", "备注"]


def _stud_col(header, name, default):
    for i, h in enumerate(header):
        if name in h:
            return i
    return default


def read_studs(directory: str = DEFAULT_INVENTORY) -> Dict[str, object]:
    """读 my_studs.csv 为行记录(list[dict]，键=表头)，供网页登记 tab 渲染。"""
    p = os.path.join(directory, "my_studs.csv")
    if not os.path.isfile(p):
        return {"exists": False, "rows": []}
    rows = _read_csv_rows(p)
    if not rows:
        return {"exists": True, "rows": []}
    header = rows[0]
    out = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        rec = {}
        for i, h in enumerate(header):
            val = (r[i].strip() if len(r) > i else "")
            if h == "种马角色名" and (val.startswith("示例") or not val):
                break
            rec[h] = val
        else:
            out.append(rec)
    return {"exists": True, "rows": out}


def save_studs(studs_rows: list, directory: str = DEFAULT_INVENTORY) -> int:
    """全量替换 my_studs.csv 的数据行（表头固定，保留）。

    studs_rows: list[dict]，键为表头名（未知键丢弃）。空角色名行会被跳过。
    """
    header = STUD_HEADERS
    # 兼容读回时已存在的表头顺序（若文件已有则沿用其表头，否则用模板表头）
    p = os.path.join(directory, "my_studs.csv")
    if os.path.isfile(p):
        try:
            existing = _read_csv_rows(p)
            if existing:
                header = existing[0]
        except Exception:
            pass
    body = []
    for rec in studs_rows or []:
        if not isinstance(rec, dict):
            continue
        nm = str(rec.get("种马角色名", "")).strip()
        if not nm or nm.startswith("示例"):
            continue
        body.append([str(rec.get(h, "")).strip() for h in header])
    rows = [header] + body
    _write_csv_rows(p, rows)
    return len(body)


def _as_int(value):
    """尽力转 int；失败返回 None（用于判断「服务端是否改过这个值」）。"""
    try:
        return int(str(value if value is not None else "").strip())
    except (TypeError, ValueError):
        return None


def _norm_awaken(awaken) -> int:
    """突破数归一到 0-4（规则见 module/umamusume/card_level.py）。"""
    if card_level is not None:
        return card_level.normalize_awaken(awaken)
    try:
        return max(0, min(4, int(awaken)))
    except (TypeError, ValueError):
        return 0


def _clamp_level(level, rarity, awaken) -> int:
    """等级钳制到 [1, 稀有度基准 + 5×突破]（单一数据源: card_level）。

    SSR 30+5a / SR 25+5a / R 20+5a；稀有度未知时按 SSR 降级。
    """
    if card_level is not None:
        return card_level.clamp_level(level, rarity, awaken)
    try:
        return max(1, min(50, int(level)))
    except (TypeError, ValueError):
        return 50


def _clean_int(r, i) -> int:
    try:
        return int(r[i].strip()) if len(r) > i and r[i].strip() else 0
    except Exception:
        return 0
