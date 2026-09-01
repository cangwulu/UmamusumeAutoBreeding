# -*- coding: utf-8 -*-
"""目标构筑育成（TargetBuild）骨架 → 首版可用草稿。

对应需求：用户在别的网站推理出每一代需要什么样的「种马」（即目标马娘），
本程序按 BuildSpec 描述的规格（技能 / 适应性 / 属性阈值）自动操纵模拟器练出这只马。

术语约定（避免歧义，见 HANDOVER-2026-09-01.md）：
    * 种马 / 目标马娘 = 用户规划好的、程序要练出来的那只马（不是游戏内繁殖机制）
    * BuildSpec      = 这一代的育成目标规格
    * TargetBuildPlanner = 按规格规划每个回合动作的规划器

本文件刻意不 import bot / cultivate，避免循环依赖，也避免「直接跑脚本」时
报 No module named 'bot'。需要 ctx 的 run() 内部再做延迟导入或接收已构造的 ctx。

设计要点（首版草稿）：
    * 决策逻辑拆成「纯函数核心」——只依赖一个普通的 BuildState（属性/技能/适应性/技能点/
      回合），不依赖模拟器。这样无需运行游戏即可单测与 CLI 演示。
    * run(ctx, spec) 是接入 cultivate.py / 真实 ctx 的集成点，仍留 TODO（需要模拟器上下文
      与你的实操细节）；但它可复用 next_action() 这个纯逻辑核心。
    * 养成「策略」本身由 BuildSpec 表达（你在外部模拟器推理出的目标），本模块负责忠实地
      把规格执行出来——选属性训练、按点名学技能、达标收手。

用法：
    from module.umamusume.script.cultivate_task.target_build import (
        BuildSpec, BUILD_PRESETS, TargetBuildPlanner, CultivateGoal, BuildState)

    planner = TargetBuildPlanner()
    action = planner.next_action(state, BUILD_PRESETS["demo_gen3_speed"], chara="特别周")

CLI（无需 bot 环境，可直接跑）：
    python module/umamusume/script/cultivate_task/target_build.py list
    python module/umamusume/script/cultivate_task/target_build.py validate demo_gen3_speed
    python module/umamusume/script/cultivate_task/target_build.py simulate demo_gen3_speed
"""

import os
import sys
import json
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# 允许「直接跑脚本」：把项目根塞进 sys.path（同 chara_skills.py 的做法）。
# target_build.py 位于 <项目根>/module/umamusume/script/cultivate_task/ 下，往上 5 层即项目根。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class CultivateGoal(Enum):
    """育成目标类型。与 cultivate.py 现有默认流程（RACE）并列。"""
    RACE = "race"   # 竞技向（现有默认逻辑）
    BUILD = "build"  # 目标构筑向（本模块）


# 属性键统一用小写英文（对齐游戏内 speed/stamina/power/guts/wisdom）
STAT_KEYS = ("speed", "stamina", "power", "guts", "wisdom")

# stat 键 → 项目真实 UmaAttribute 字段名。
# 注意：游戏通用词 guts/wisdom 在本项目代码里叫 will/intelligence，
# 离线模拟无所谓，但 build_state_from_ctx 读真实 ctx 时务必映射正确。
STAT_TO_ATTR = {
    "speed": "speed",
    "stamina": "stamina",
    "power": "power",
    "guts": "will",          # 毅力
    "wisdom": "intelligence",  # 智力
}

# 适应性等级排序（用于比对当前等级是否达到要求）。空串/未知按最低处理。
GRADE_RANK = {"": 0, "?": 0, "E": 1, "D": 2, "C": 3, "B": 4, "A": 5, "S": 6}


@dataclass
class BuildSpec:
    """一代育成的目标规格——用户在程序内手动填写。

    Attributes:
        name: 规格代号，如 "gen3_speed"
        chara: 可选，正在育成的马娘名（用于剔除其自带技能，避免白花技能点）
        skills: 目标技能名列表（如 ["流星", "圆弧"]），规划器优先学这些
        aptitudes: 适应性要求，如 {"芝": "S", "林道": "B"}
        stat_goals: 属性阈值，如 {"speed": 1200, "power": 900}
        priority: 取舍策略（属性 vs 技能冲突时）：
                  "balanced" 均衡 / "stat_first" 优先属性 / "skill_first" 优先技能
    """

    name: str
    chara: Optional[str] = None
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


@dataclass
class BuildState:
    """某一时刻的育成进度快照（纯数据，便于单测与模拟，不依赖模拟器）。

    Attributes:
        stats: 当前五维属性 {speed/stamina/power/guts/wisdom: int}
        owned_skills: 已学会的技能名（含已学 / 自带）
        aptitudes: 当前适应性 {场地/跑法/距离等: 等级}
        skill_points: 当前可用技能点
        turn: 当前回合（从 0 计）
        max_turns: 育成总回合数（用于模拟收尾）
    """

    stats: Dict[str, int] = field(default_factory=dict)
    owned_skills: List[str] = field(default_factory=list)
    aptitudes: Dict[str, str] = field(default_factory=dict)
    skill_points: int = 0
    turn: int = 0
    max_turns: int = 0


# ===== 用户手动填写每一代规格的地方 ↓↓↓ =====
# 下面 demo_gen3_speed 仅作功能演示：请改成你实际在外部模拟器推理出的每一代规格。
# chara 填正在育成的马娘名，可让规划器自动跳过其自带技能（如特别周的固有「流星」）。
BUILD_PRESETS: Dict[str, BuildSpec] = {
    "demo_gen3_speed": BuildSpec(
        name="demo_gen3_speed",
        chara="特别周",                       # 可选：填正在育成的马娘名
        skills=["流星", "圆弧"],              # 流星是特别周自带 → 自动跳过；圆弧会被学习
        aptitudes={"芝": "S"},
        stat_goals={"speed": 1200, "power": 900},
        priority="stat_first",
    ),
    # 你的实际规格写在这里（取消注释并修改）：
    # "gen3_speed": BuildSpec(
    #     name="gen3_speed",
    #     chara="...",
    #     skills=["...", "..."],
    #     aptitudes={"芝": "S", "林道": "B"},
    #     stat_goals={"speed": 1200, "power": 900},
    #     priority="stat_first",
    # ),
}
# ===== 用户手动填写每一代规格的地方 ↑↑↑ =====


def _chara_skill_module():
    """延迟加载 chara_skills 模块（用于剔除马娘自带技能）。

    走「按文件路径直接 importlib 加载」绕开 asset/__init__（其会 import cv2），
    使本模块在没有 cv2 的纯逻辑 / CLI 环境下也能用上建议去重能力。
    失败（如缺数据文件）返回 None，调用方需降级处理。
    """
    try:
        import importlib.util
        path = os.path.join(_PROJECT_ROOT, "module", "umamusume",
                            "asset", "chara_skills.py")
        mod_spec = importlib.util.spec_from_file_location("chara_skills_direct", path)
        mod = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def build_state_from_ctx(ctx, chara: Optional[str] = None) -> Optional["BuildState"]:
    """从真实 UmamusumeContext 构造 BuildState（接入 cultivate.py 时由钩子调用）。

    只读、不操纵；任何字段缺失/异常都返回 None，让调用方安全回退到原流程。
    用户侧 stat 键（guts/wisdom）会按 STAT_TO_ATTR 映射到真实字段（will/intelligence）。
    """
    try:
        ti = ctx.cultivate_detail.turn_info
        if ti is None:
            return None
        attr = ti.uma_attribute
        if attr is None:
            return None
        stats = {}
        for k in STAT_KEYS:
            field_name = STAT_TO_ATTR.get(k, k)
            stats[k] = int(getattr(attr, field_name, 0) or 0)
        skill_points = int(getattr(attr, "skill_point", 0) or 0)
        owned = []
        try:
            owned = list(getattr(ctx.cultivate_detail, "learned_skill_names", []) or [])
        except Exception:
            owned = []
        aptitudes = {}
        try:
            aptitudes = dict(getattr(ctx.cultivate_detail, "aptitudes", {}) or {})
        except Exception:
            aptitudes = {}
        return BuildState(
            stats=stats,
            owned_skills=owned,
            aptitudes=aptitudes,
            skill_points=skill_points,
            turn=int(getattr(ti, "date", 0) or 0),
        )
    except Exception:
        return None


class TargetBuildPlanner:
    """按 BuildSpec 规划育成动作。

    首版草稿：决策逻辑已实现为「纯函数核心」（不依赖模拟器，可单测）；
    集成到真实 ctx 的 run() 仍留 TODO。
    """

    def __init__(self, spec: Optional[BuildSpec] = None):
        self.spec = spec

    # ---- 对外主入口（给 cultivate.py 调用） ----

    def run(self, ctx, spec: Optional[BuildSpec] = None) -> None:
        """执行一代目标构筑育成（高层编排器，可选）。

        首版已通过 cultivate.py 的 per-turn 钩子实现集成：每回合钩子调用
        build_state_from_ctx(ctx) 读状态 → next_action() 出决策 → 写回
        ctx.cultivate_detail.turn_info.turn_operation（训练/休息）或 learn_skill_list（学技能）。
        本方法保留为可选的高层循环编排入口；当前仍抛 NotImplementedError，避免在没有
        完整 ctx / 真实游戏会话时误执行。
        """
        spec = spec or self.spec
        if spec is None:
            raise ValueError("TargetBuildPlanner.run 需要一个 BuildSpec")
        raise NotImplementedError("TargetBuildPlanner.run 高层编排待实现（per-turn 钩子已可用）")

    # ---- 纯逻辑决策核心（可单测、可 CLI 演示） ----

    def choose_training(self, state: BuildState, spec: BuildSpec) -> Optional[str]:
        """决定本回合练哪个属性：选「未达标且缺口最大」的属性。

        全部达标则返回 None（无需再练属性）。
        """
        gaps = {
            k: spec.stat_goals.get(k, 0) - state.stats.get(k, 0)
            for k in spec.stat_goals
        }
        gaps = {k: v for k, v in gaps.items() if v > 0}
        if not gaps:
            return None
        return max(gaps, key=gaps.get)

    def choose_skills_to_learn(self, state: BuildState, spec: BuildSpec,
                               chara: Optional[str] = None) -> List[str]:
        """返回本回合应学习的技能名列表（优先 spec.skills 点名技能）。

        会用 chara_skills.suggest_not_to_learn 剔除马娘已自带的，避免白花技能点。
        返回的是候选集合；是否真的学、学几个，由调用方（next_action / run）按技能点裁定。
        """
        want = [s for s in spec.skills if s not in state.owned_skills]
        cs = _chara_skill_module()
        if chara and cs is not None:
            try:
                res = cs.suggest_not_to_learn(chara, want)
                # 返回 (待学列表, 已自带列表) 或纯列表，取「待学」部分
                if isinstance(res, tuple) and len(res) >= 1:
                    want = list(res[0])
                else:
                    want = list(res)
            except Exception:
                pass
        return want

    def spec_met(self, state: BuildState, spec: BuildSpec,
                 chara: Optional[str] = None) -> bool:
        """当前进度是否满足规格，满足即收手。"""
        # 1) 属性阈值全部达标
        for k, goal in spec.stat_goals.items():
            if state.stats.get(k, 0) < goal:
                return False
        # 2) 点名技能全部到手（自带技能视为已满足）
        cs = _chara_skill_module()
        for s in spec.skills:
            if s in state.owned_skills:
                continue
            if chara and cs is not None:
                try:
                    if cs.is_owned(chara, s):
                        continue
                except Exception:
                    pass
            return False
        # 3) 适应性要求全部满足（当前等级 >= 要求等级）
        for k, need in spec.aptitudes.items():
            have = state.aptitudes.get(k, "")
            if GRADE_RANK.get(have, 0) < GRADE_RANK.get(need, 0):
                return False
        return True

    def evaluate_aptitude(self, state: BuildState, spec: BuildSpec) -> float:
        """评估当前适应性达标程度（0~1），用于取舍与展示。"""
        if not spec.aptitudes:
            return 1.0
        ok = 0
        for k, need in spec.aptitudes.items():
            have = state.aptitudes.get(k, "")
            if GRADE_RANK.get(have, 0) >= GRADE_RANK.get(need, 0):
                ok += 1
        return ok / len(spec.aptitudes)

    def next_action(self, state: BuildState, spec: BuildSpec,
                    chara: Optional[str] = None) -> Dict:
        """给出本回合的下一步动作（纯逻辑，供 run()/模拟调用）。

        返回结构：
            {"type": "done"}                  规格已满足，收手
            {"type": "learn", "skills": [...]} 本回合学这些技能
            {"type": "train", "stat": "speed"} 本回合练该属性
            {"type": "rest"}                   兜底：无明确动作时休息
        """
        if self.spec_met(state, spec, chara):
            return {"type": "done"}

        skills = self.choose_skills_to_learn(state, spec, chara)
        can_learn = bool(skills) and state.skill_points > 0

        # 优先级裁定：先属性还是先技能
        if spec.priority == "skill_first" and can_learn:
            return {"type": "learn", "skills": skills}
        if spec.priority == "stat_first":
            train = self.choose_training(state, spec)
            if train:
                return {"type": "train", "stat": train}
            if can_learn:
                return {"type": "learn", "skills": skills}
            return {"type": "rest"}
        # balanced：属性未达标先补属性；属性达标但还有技能点则学技能
        train = self.choose_training(state, spec)
        if train:
            return {"type": "train", "stat": train}
        if can_learn:
            return {"type": "learn", "skills": skills}
        return {"type": "rest"}


def select_cultivate_strategy(goal: CultivateGoal, spec: Optional[BuildSpec] = None):
    """cultivate.py 的策略分发入口（挂接点）。

    RACE  -> 返回 None，沿用 cultivate.py 原流程
    BUILD -> 返回 TargetBuildPlanner(spec)
    """
    if goal == CultivateGoal.BUILD:
        return TargetBuildPlanner(spec)
    return None


# ===================== CLI =====================

def _simulate(spec: BuildSpec) -> int:
    """用一份假状态跑完一代，演示 next_action 的决策流（无需模拟器）。"""
    chara = spec.chara
    state = BuildState(
        stats={k: 300 for k in STAT_KEYS},
        owned_skills=[],
        aptitudes={"芝": "S", "林道": "B"},   # 满足示例适应性
        skill_points=5000,
        turn=0,
        max_turns=60,
    )
    planner = TargetBuildPlanner(spec)
    print("=== 模拟 %s（chara=%s）===" % (spec.name, chara))
    while state.turn < state.max_turns:
        act = planner.next_action(state, spec, chara)
        if act["type"] == "done":
            print("第 %d 回合：规格满足，收手 ✓" % state.turn)
            break
        if act["type"] == "train":
            state.stats[act["stat"]] += 80
            print("第 %d 回合：练 %s → %d" % (state.turn, act["stat"], state.stats[act["stat"]]))
        elif act["type"] == "learn":
            for s in act["skills"]:
                if s not in state.owned_skills:
                    state.owned_skills.append(s)
            print("第 %d 回合：学技能 %s" % (state.turn, act["skills"]))
        elif act["type"] == "rest":
            print("第 %d 回合：休息（无明确动作）")
        state.turn += 1
    met = planner.spec_met(state, spec, chara)
    print("--- 结果：met=%s stats=%s owned=%s apt=%.2f" % (
        met, state.stats, state.owned_skills, planner.evaluate_aptitude(state, spec)))
    return 0 if met else 1


def _main(argv: List[str]) -> int:
    """CLI：列出 / 校验 / 模拟 BUILD_PRESETS。"""
    if not argv or argv[0] in ("-h", "--help", "list"):
        print("可用 BuildSpec 预设：")
        if not BUILD_PRESETS:
            print("  （空）在 target_build.py 的 BUILD_PRESETS 中手动填写")
        for name, spec in BUILD_PRESETS.items():
            print("  - %s: chara=%s skills=%s stats=%s" % (
                name, spec.chara, spec.skills, spec.stat_goals))
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
    if argv[0] == "simulate":
        rc = 0
        for name in argv[1:] or list(BUILD_PRESETS.keys()):
            spec = BUILD_PRESETS.get(name)
            if spec is None:
                print("[未找到] %s" % name)
                rc = 1
                continue
            if _simulate(spec) != 0:
                rc = 1
        return rc
    print("未知子命令: %s（可用 list / validate / simulate）" % argv[0])
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
