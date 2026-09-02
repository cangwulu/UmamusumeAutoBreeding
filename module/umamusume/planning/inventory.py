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
