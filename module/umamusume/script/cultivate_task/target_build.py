# -*- coding: utf-8 -*-
"""目标构筑育成（TargetBuild）骨架。

对应需求：用户在别的网站推理出每一代需要什么样的「种马」（即目标马娘），
本程序按 BuildSpec 描述的规格（技能 / 适应性 / 属性阈值）自动操纵模拟器练出这只马。

术语约定（避免歧义，见 HANDOVER-2026-09-01.md）：
    * 种马 / 目标马娘 = 用户规划好的、程序要练出来的那只马（不是游戏内繁殖机制）
    * BuildSpec      = 这一代的育成目标规格
    * TargetBuildPlanner = 按规格规划每个回合动作的规划器

本文件是「骨架」：数据结构和对外接口已定，策略决策逻辑（如何选训练、如何学技能、
何时收手）留 TODO，由后续填入——这部分需要你的养成攻略知识。

设计要点：
    * 本模块刻意不 import bot / cultivate，避免循环依赖，也避免「直接跑脚本」时
      报 No module named 'bot'。需要 ctx 的方法内部再做延迟导入或接收已构造的 ctx。
    * 与现有 cultivate.py 通过 CultivateGoal 枚举 + select_cultivate_strategy() 挂接：
      RACE 沿用现有默认逻辑，BUILD 路由到 TargetBuildPlanner。

用法：
    from module.umamusume.script.cultivate_task.target_build import (
        BuildSpec, BUILD_PRESETS, TargetBuildPlanner, CultivateGoal)
    planner = TargetBuildPlanner()
    planner.run(ctx, BUILD_PRESETS["gen3_speed"])

CLI（无需 bot 环境，可直接跑）：
    python module/umamusume/script/cultivate_task/target_build.py list
    python module/umamusume/script/cultivate_task/target_build.py validate gen3_speed
"""

import os
import sys
import json
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# 允许「直接跑脚本」：把项目根塞进 sys.path（同 chara_skills.py 的做法）。
# target_build.py 位于 <项目根>/module/umamusume/script/cultivate_task/ 下，往上 4 层即项目根。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class CultivateGoal(Enum):
    """育成目标类型。与 cultivate.py 现有默认流程（RACE）并列。"""
    RACE = "race"   # 竞技向（现有默认逻辑）
    BUILD = "build"  # 目标构筑向（本模块）


# 属性键统一用小写英文（对齐游戏内 speed/stamina/power/guts/wisdom）
STAT_KEYS = ("speed", "stamina", "power", "guts", "wisdom")


@dataclass
class BuildSpec:
    """一代育成的目标规格——用户在程序内手动填写。

    Attributes:
        name: 规格代号，如 "gen3_speed"
        skills: 目标技能名列表（如 ["流星", "圆弧"]），规划器优先学这些
        aptitudes: 适应性要求，如 {"芝": "S", "林道": "B"}
        stat_goals: 属性阈值，如 {"speed": 1200, "power": 900}
        priority: 取舍策略（属性 vs 技能冲突时）：
                  "balanced" 均衡 / "stat_first" 优先属性 / "skill_first" 优先技能
    """

    name: str
    skills: List[str] = field(default_factory=list)
    aptitudes: Dict[str, str] = field(default_factory=dict)
    stat_goals: Dict[str, int] = field(default_factory=dict)
    priority: str = "balanced"

    def validate(self) -> List[str]:
        """返回问题列表，空列表表示规格合法。"""
        problems: List[str] = []
        for k in self.stat_goals:
            if k not in STAT_KEYS:
                problems.append("未知属性键: %s（合法: %s）" % (k, STAT_KEYS))
        if self.priority not in ("balanced", "stat_first", "skill_first"):
            problems.append("未知 priority: %s" % self.priority)
        return problems


# ===== 用户手动填写每一代规格的地方 ↓↓↓ =====
BUILD_PRESETS: Dict[str, BuildSpec] = {
    # 示例（取消注释并改成你的实际规格）：
    # "gen3_speed": BuildSpec(
    #     name="gen3_speed",
    #     skills=["流星", "圆弧"],
    #     aptitudes={"芝": "S", "林道": "B"},
    #     stat_goals={"speed": 1200, "power": 900},
    #     priority="stat_first",
    # ),
}
# ===== 用户手动填写每一代规格的地方 ↑↑↑ =====


class TargetBuildPlanner:
    """按 BuildSpec 规划育成动作。

    骨架阶段：所有决策方法留 TODO，由你的养成攻略知识填充。
    """

    def __init__(self, spec: Optional[BuildSpec] = None):
        self.spec = spec

    # ---- 对外主入口（给 cultivate.py 调用） ----

    def run(self, ctx, spec: Optional[BuildSpec] = None) -> None:
        """执行一代目标构筑育成。

        TODO: 实现主循环——轮询 ctx 状态，调用下面的决策方法，操纵模拟器。
        参考 cultivate.py 的 script_cultivate_main_menu 流程。
        """
        spec = spec or self.spec
        if spec is None:
            raise ValueError("TargetBuildPlanner.run 需要一个 BuildSpec")
        raise NotImplementedError("TargetBuildPlanner.run 待实现：填入养成攻略逻辑")

    # ---- 决策方法（攻略知识填入处） ----

    def choose_training(self, ctx, spec: BuildSpec):
        """决定本回合练哪个属性 / 参加什么。

        TODO: 依据 spec.stat_goals 与当前属性差距、体力、事件，选最优训练。
        可复用 module.umamusume.asset.skill_order 的评价分排序思路评估训练收益。
        """
        raise NotImplementedError

    def choose_skills_to_learn(self, ctx, spec: BuildSpec) -> List[str]:
        """返回本回合应学习的技能名列表（优先 spec.skills 点名技能）。

        TODO: 与现有技能学习贪心逻辑不同，这里优先 spec.skills 里用户指定技能；
        并用 chara_skills.suggest_not_to_learn 剔除马娘已自带的，避免白花技能点。
        """
        raise NotImplementedError

    def spec_met(self, ctx, spec: BuildSpec) -> bool:
        """当前进度是否满足规格，满足即收手。

        TODO: 读取 ctx.cultivate_detail 的属性 / 技能，与 spec 比对。
        """
        raise NotImplementedError

    def evaluate_aptitude(self, ctx, spec: BuildSpec) -> float:
        """评估当前适应性达标程度（0~1），用于取舍。

        TODO: 与 spec.aptitudes 比对当前场地 / 距离适应性。
        """
        raise NotImplementedError


def select_cultivate_strategy(goal: CultivateGoal, spec: Optional[BuildSpec] = None):
    """cultivate.py 的策略分发入口（挂接点）。

    RACE  -> 返回 None，沿用 cultivate.py 原流程
    BUILD -> 返回 TargetBuildPlanner(spec)
    """
    if goal == CultivateGoal.BUILD:
        return TargetBuildPlanner(spec)
    return None


def _main(argv: List[str]) -> int:
    """极简 CLI：列出 / 校验 BUILD_PRESETS。"""
    if not argv or argv[0] in ("-h", "--help", "list"):
        print("可用 BuildSpec 预设：")
        if not BUILD_PRESETS:
            print("  （空）在 target_build.py 的 BUILD_PRESETS 中手动填写")
        for name, spec in BUILD_PRESETS.items():
            print("  - %s: skills=%s stats=%s" % (name, spec.skills, spec.stat_goals))
        return 0
    if argv[0] == "validate":
        rc = 0
        for name in argv[1:]:
            spec = BUILD_PRESETS.get(name)
            if spec is None:
                print("[未找到] %s" % name)
                rc = 1
                continue
            problems = spec.validate()
            if problems:
                print("[%s] 规格问题: %s" % (name, problems))
                rc = 1
            else:
                print("[%s] 规格合法" % name)
        return rc
    print("未知子命令: %s（可用 list / validate）" % argv[0])
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
