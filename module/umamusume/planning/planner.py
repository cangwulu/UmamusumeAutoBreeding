# -*- coding: utf-8 -*-
"""PlanService: 由大赛情报 + 库存产出逐代养成计划。

算法复用 asset/stud_planner（plan/load_inventory），本层负责:
- CupInfo -> Track 转换与合法性把关
- 输出 md 报告(render_report) + 精简 json(供后续确认/队列消费)
"""

import datetime
import json
import os
import sys
from typing import Dict, Optional

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_PKG_DIR)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from module.umamusume.planning.cup_info import CupInfo, load_cup
from module.umamusume.planning import inventory as inventory_service

try:
    from module.umamusume.asset import stud_planner
except Exception as exc:  # pragma: no cover
    stud_planner = None
    _IMPORT_ERR = exc
else:
    _IMPORT_ERR = None


def ensure_import():
    if stud_planner is None:
        raise RuntimeError("无法导入 asset/stud_planner: %r" % (_IMPORT_ERR,))


def _result_to_summary(result: Dict[str, object], inv_dir: str,
                       inv=None) -> Dict[str, object]:
    """把 plan() 返回(含 Chara/Track 等对象)压成可 JSON 序列化的摘要。"""
    ensure_import()
    track = result["track"]
    candidates = []
    for det in result.get("candidates", []):
        score = det["score"]
        chara = score["chara"]
        req = det.get("requirements", {})
        candidates.append({
            "card_name": chara.card_name,
            "name": chara.name,
            "total": score.get("total", 0),
            "score_detail": {k: v for k, v in score.items() if k != "chara"},
            "factor_gap": req.get("summary") or req.get("gaps") or {},
        })
    summary = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "inventory_dir": inv_dir,
        "track": {
            "race_name": getattr(track, "name", ""),
            "venue": track.venue, "distance": track.distance,
            "surface": track.surface, "direction": track.direction,
            "weather": track.weather, "condition": track.condition,
            "distance_class": track.distance_class,
        },
        "style": result["style"],
        "stats_goal": result["stats_goal"],
        "apt_goal": {k: str(v) for k, v in result["apt_goal"].items()},
        "candidate_top": candidates,
        "inventory_empty": result["inventory_empty"],
    }
    # 行动清单：借位 / 卡升级 / 马娘状态（5 自产 + 1 借 口径）
    if inv is not None:
        try:
            summary["prep"] = stud_planner.build_action_items(result, inv)
        except Exception as exc:  # 建议是附加信息, 失败不应拖垮主结果
            summary["prep"] = {"_error": str(exc)}
    return summary


def plan(cup: CupInfo, inv_dir: str = None, top: int = 5,
         out_dir: str = None) -> Dict[str, object]:
    """执行规划, 返回 {'result':..., 'md_path':..., 'json_path':...}。"""
    ensure_import()
    inv_dir = inv_dir or inventory_service.DEFAULT_INVENTORY
    out_dir = out_dir or inv_dir

    errs = cup.validate()
    if errs:
        raise ValueError("大赛情报不合法:\n  - " + "\n  - ".join(errs))

    inv = stud_planner.load_inventory(inv_dir)
    track = _cup_to_track(cup)

    result = stud_planner.plan(track, inv, style=cup.style, top=top)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, "plan_%s.md" % stamp)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(stud_planner.render_report(result, inv))

    json_path = os.path.join(out_dir, "plan_%s.json" % stamp)
    summary = _result_to_summary(result, inv_dir, inv=inv)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return {"result": result, "summary": summary,
            "md_path": md_path, "json_path": json_path}


def _cup_to_track(cup: CupInfo):
    """CupInfo -> stud_planner.Track（由字段构造, 不依赖 cup 扩展方法）。"""
    ensure_import()
    return stud_planner.Track(
        venue=cup.venue, distance=int(cup.distance), surface=cup.surface,
        direction=cup.direction, weather=cup.weather, condition=cup.condition,
        name=cup.race_name)
