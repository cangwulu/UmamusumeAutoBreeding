# -*- coding: utf-8 -*-
"""CupService: 大赛情报录入/查证/持久化 (my_inventory/cup_info.json)."""

import datetime
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict, Optional

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
# planning/ -> umamusume -> module -> 项目根
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_PKG_DIR)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

DEFAULT_CUP_FILE = os.path.join(_PROJECT_ROOT, "my_inventory", "cup_info.json")

# 合法值域（与 stud_planner 对齐）
SURFACES = ("草地", "泥地")
DIRECTIONS = ("左", "右")
WEATHERS = ("晴", "阴", "雨", "雪", "小雪", "暴雨")
CONDITIONS = ("良", "稍重", "重", "不良")
STYLES = ("逃", "先", "差", "追")


@dataclass
class CupInfo:
    """一场大赛的赛道条件（长期保存, 供规划/育成多次复用）。"""

    race_name: str = ""          # 比赛名（--race 自动查证时填充; 空=自定义赛道）
    venue: str = ""              # 场地: 中山/东京/...
    distance: int = 2000         # 距离(米)
    surface: str = "草地"
    direction: str = "右"
    weather: str = "晴"
    condition: str = "良"
    style: str = "差"            # 预判主流跑法: 逃/先/差/追
    note: str = ""               # 备注: 大赛日期/BP/环境等自由文本
    updated_at: str = ""         # 自动: 本地时间

    def __post_init__(self):
        self.surface = self.surface or "草地"
        self.condition = self.condition or "良"
        self.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- 持久化 ----
    def save(self, path: str = DEFAULT_CUP_FILE) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, path: str = DEFAULT_CUP_FILE) -> Optional["CupInfo"]:
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            allowed = {f.name for f in cls.__dataclass_fields__.values()}
            return cls(**{k: v for k, v in data.items() if k in allowed})
        except Exception as exc:  # 文件损坏时给出明确提示而非静默
            print("[错误] cup_info.json 解析失败: %s (%s)" % (path, exc), file=sys.stderr)
            return None

    # ---- 展示 ----
    def label(self) -> str:
        parts = ["%s%s %dm %s回" % (self.venue or "?", self.surface, self.distance,
                                    self.direction),
                 "%s场" % self.condition]
        if self.weather:
            parts.append(self.weather)
        parts.append(STYLES_CN.get(self.style, self.style))
        label = " · ".join(parts)
        if self.race_name:
            label += "  [%s]" % self.race_name
        return label

    def validate(self) -> list:
        """返回不合法项列表（空=通过）。"""
        errs = []
        if not self.venue:
            errs.append("venue 场地缺失（用 --race 查证或手填 --venue）")
        if not (1000 <= self.distance <= 3600):
            errs.append("distance 超出合理范围(1000-3600): %s" % self.distance)
        if self.surface not in SURFACES:
            errs.append("surface 需 ∈ %s: %s" % (SURFACES, self.surface))
        if self.direction not in DIRECTIONS:
            errs.append("direction 需 ∈ %s: %s" % (DIRECTIONS, self.direction))
        if self.weather not in WEATHERS:
            errs.append("weather 需 ∈ %s: %s" % (WEATHERS, self.weather))
        if self.condition not in CONDITIONS:
            errs.append("condition 需 ∈ %s: %s" % (CONDITIONS, self.condition))
        if self.style not in STYLES:
            errs.append("style 需 ∈ %s: %s" % (STYLES, self.style))
        return errs


STYLES_CN = {"逃": "逃马", "先": "先行", "差": "差马", "追": "追马"}


def save_cup(cup: CupInfo, path: str = DEFAULT_CUP_FILE) -> str:
    saved = cup.save(path)
    print("大赛情报已保存: %s" % saved)
    print("  " + cup.label())
    return saved


def load_cup(path: str = DEFAULT_CUP_FILE) -> Optional[CupInfo]:
    cup = CupInfo.load(path)
    if cup is None:
        print("[提示] 尚未登记大赛情报。请先运行:", file=sys.stderr)
        print("  python -m module.umamusume.planning cup --race 中山大奖赛", file=sys.stderr)
        print("  或: python -m module.umamusume.planning cup --venue 中山 --distance 2500 ...", file=sys.stderr)
    return cup
