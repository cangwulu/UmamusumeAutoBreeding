# -*- coding: utf-8 -*-
"""规划统一 CLI。

用法:
  python -m module.umamusume.planning check                 # 库存体检
  python -m module.umamusume.planning cup --race 中山大奖赛  # 大赛情报(比赛名查证)
  python -m module.umamusume.planning cup --venue 中山 --distance 2500 --track 草地 --direction 右 --weather 晴 --condition 良 --style 差
  python -m module.umamusume.planning plan                   # 用已存 cup_info.json 出计划
  python -m module.umamusume.planning plan --top 8

产物: my_inventory/cup_info.json + my_inventory/plan_<时间戳>.md/.json
"""

import argparse
import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_PKG_DIR)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from module.umamusume.planning import inventory as inventory_service
from module.umamusume.planning import planner as planner_service
from module.umamusume.planning.cup_info import (CONDITIONS, DIRECTIONS,
                                                DEFAULT_CUP_FILE, STYLES,
                                                SURFACES, WEATHERS, CupInfo,
                                                load_cup, save_cup)


def _cmd_check(args) -> int:
    rep = inventory_service.check(args.inventory)
    print("库存目录: %s" % rep["directory"])
    print("  马娘: %d 只 | 协助卡: %d 张 | 成品种马: %d 只" % (
        rep["characters"], rep["cards"], rep["studs"]))
    for p in rep["problems"]:
        print("  [注意] " + p)
    if not rep["problems"]:
        print("  库存填报 OK。")
    return 0 if not rep["problems"] else 1


def _resolve_track_from_race(name: str):
    """按比赛名反查赛道(Track), 失败返回 None。"""
    try:
        from module.umamusume.asset import stud_planner
    except Exception as exc:
        print("[错误] 无法加载 stud_planner: %r" % exc, file=sys.stderr)
        return None
    return stud_planner._track_from_race(name)


def _suggest_races(name: str, top: int = 3) -> list:
    """查证失败时给出相近比赛名候选（覆盖简中/日文写法差异）。"""
    import difflib
    try:
        from module.umamusume.asset import stud_planner
        data = stud_planner.load_json("race_bwiki.json")
    except Exception:
        return []
    pool = []
    for r in data.get("races", []):
        for key in (r.get("name"), r.get("jp_name"), r.get("name_zh"),
                    r.get("alias", "")):
            if key:
                pool.append(key)
    return difflib.get_close_matches(name, sorted(set(pool)), n=top, cutoff=0.4)


def _cmd_cup(args) -> int:
    cup = CupInfo.load(args.file) or CupInfo()
    if args.race:
        t = _resolve_track_from_race(args.race)
        if t is None:
            print("[错误] 未在比赛库找到: %s（可改用 --venue/--distance 手填）" % args.race,
                  file=sys.stderr)
            sugg = _suggest_races(args.race)
            if sugg:
                print("相近比赛名: %s" % " / ".join(sugg), file=sys.stderr)
            return 2
        cup.race_name = t.name or args.race
        cup.venue = t.venue
        cup.distance = t.distance
        cup.surface = t.surface
        cup.direction = t.direction
    elif args.venue or args.distance is not None:
        # 显式手填赛道 = 自定义大赛, 清掉可能残留的比赛名
        cup.race_name = ""
    # 手填参数覆盖
    for field, val in (("venue", args.venue), ("surface", args.surface),
                       ("direction", args.direction), ("weather", args.weather),
                       ("condition", args.condition), ("style", args.style),
                       ("note", args.note)):
        if val is not None and val != "":
            setattr(cup, field, val)
    if args.distance is not None:
        cup.distance = args.distance

    errs = cup.validate()
    if errs:
        print("大赛情报不合法:", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 2
    save_cup(cup, args.file)
    return 0


def _cmd_plan(args) -> int:
    if args.cup_file:
        cup = CupInfo.load(args.cup_file)
        if cup is None:
            return 2
    else:
        cup = load_cup(args.file)
        if cup is None:
            return 2
    try:
        out = planner_service.plan(cup, inv_dir=args.inventory, top=args.top)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 保留回溯便于排查
        import traceback
        traceback.print_exc()
        print("[错误] 规划失败: %s" % exc, file=sys.stderr)
        return 1

    # 控制台摘要: 复用 render 的 print_summary
    try:
        from module.umamusume.asset import stud_planner
        inv = stud_planner.load_inventory(args.inventory)
        stud_planner.print_summary(out["result"], inv, top=args.top)
    except Exception:
        pass
    print("计划已写入:")
    print("  " + out["md_path"])
    print("  " + out["json_path"])
    return 0


def _cmd_show(args) -> int:
    """查看已登记的大赛情报。"""
    cup = CupInfo.load(args.file)
    if cup is None:
        print("[提示] 尚未登记大赛情报。", file=sys.stderr)
        return 1
    print(cup.label())
    print("比赛名: %s" % (cup.race_name or "(自定义)"))
    print("备注:   %s" % (cup.note or "(无)"))
    print("更新于: %s" % cup.updated_at)
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(prog="umamusume-plan",
                                 description="大赛情报 → 种马规划 (M1 规划闭环)")
    sub = ap.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="库存体检")
    p_check.add_argument("--inventory", default=inventory_service.DEFAULT_INVENTORY)
    p_check.set_defaults(func=_cmd_check)

    p_cup = sub.add_parser("cup", help="登记/更新大赛情报")
    p_cup.add_argument("--race", default="", help="比赛名(从比赛库自动查证)")
    p_cup.add_argument("--venue", default="")
    p_cup.add_argument("--distance", type=int)
    p_cup.add_argument("--track", dest="surface", default="",
                       help="草地/泥地")
    p_cup.add_argument("--direction", default="", choices=DIRECTIONS)
    p_cup.add_argument("--weather", default="", choices=WEATHERS)
    p_cup.add_argument("--condition", default="", choices=CONDITIONS)
    p_cup.add_argument("--style", default="", choices=STYLES,
                       help="预判主流跑法 逃/先/差/追")
    p_cup.add_argument("--note", default="")
    p_cup.add_argument("--file", default=DEFAULT_CUP_FILE)
    p_cup.set_defaults(func=_cmd_cup)

    p_plan = sub.add_parser("plan", help="按已登记大赛情报出种马计划")
    p_plan.add_argument("--top", type=int, default=5)
    p_plan.add_argument("--inventory", default=inventory_service.DEFAULT_INVENTORY)
    p_plan.add_argument("--file", default=DEFAULT_CUP_FILE,
                        help="cup_info.json 路径")
    p_plan.add_argument("--cup-file", default="",
                        help="临时指定其它 cup json(不写默认文件)")
    p_plan.set_defaults(func=_cmd_plan)

    p_show = sub.add_parser("show", help="查看已登记大赛情报")
    p_show.add_argument("--file", default=DEFAULT_CUP_FILE)
    p_show.set_defaults(func=_cmd_show)

    args = ap.parse_args(argv)
    if not getattr(args, "command", None):
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
