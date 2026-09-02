from typing import Union

from bot.recog.ocr import find_similar_text
from module.umamusume.context import UmamusumeContext
from module.umamusume.script.cultivate_task.event.scenario_event import *
import bot.base.log as logger

log = logger.get_logger(__name__)

# ---- 硬编码事件（人工规则优先：新年按体力、青春杯按队名等） ----
event_map: dict[str, Union[callable, int]] = {
    "安心～针灸师，登☆场": 5,
    "新年的抱负": scenario_event_1,
    "新年参拜": scenario_event_2,
    "新年祈福": scenario_event_2,

    # 青春杯事件
    "新手教程": 2,
    "团队成员终于集结完毕!": aoharuhai_team_name_event
}

event_name_list: list[str] = [*event_map]


# ---- 事件库（event_db.json）智能选择层：懒加载 + importlib 绕 cv2 ----
_EVENT_DB = None


def _load_event_db():
    """加载事件库模块（asset/event_db.py）。

    asset/__init__.py 会 import cv2（无 cv2 时整包不可用），这里按文件路径
    importlib 单文件加载，绕开 __init__ 副作用。
    """
    global _EVENT_DB
    if _EVENT_DB is not None:
        return _EVENT_DB
    import importlib.util
    import os
    # 本文件在 <根>/module/umamusume/script/cultivate_task/event/ 下，往上 5 层到项目根
    root = os.path.abspath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", ".."))
    path = os.path.join(root, "module", "umamusume", "asset", "event_db.py")
    try:
        spec = importlib.util.spec_from_file_location("_ev_event_db", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _EVENT_DB = mod
    except Exception as exc:
        log.warning("事件库加载失败（%s），回退到仅硬编码事件", exc)
        _EVENT_DB = False
    return _EVENT_DB


def _smart_choice(ctx: UmamusumeContext, event_name: str) -> int:
    """事件库智能选层：命中库 → 问优选策略(strategy.choose_option)。

    决策链（实现计划第四节）：
        硬编码 → 查库 → 问策略(strategy.py) → 兜底选项 1
    """
    from module.umamusume.script.cultivate_task.event.strategy import choose_option
    mod = _load_event_db()
    if not mod:
        return 0
    try:
        db = mod.get_event_db()
        match = db.search_by_name([event_name], min_score=0.55)
        if match is None or not match.event:
            log.debug("未知事件[%s]，事件库未命中，走默认", event_name)
            return 0
        ev = match.event
        log.info("事件库命中[%s]（相似 %.2f），问优选策略",
                 match.name, match.score)
        return choose_option(ctx, event_name, ev) or 0
    except Exception as exc:
        log.warning("事件库智能选择异常：%s", exc)
        return 0


def get_event_choice(ctx: UmamusumeContext, event_name: str) -> int:
    event_name_normalized = find_similar_text(event_name, event_name_list, 0.8)
    if event_name_normalized != "":
        if event_name_normalized in event_map:
            opt = event_map[event_name_normalized]
            if type(opt) is int:
                return opt
            if callable(opt):
                return opt(ctx)
            else:
                log.warning("事件[%s]未提供处理逻辑", event_name_normalized)
                return 1

    # 事件库智能选择：命中并按上下文打分
    smart = _smart_choice(ctx, event_name)
    if smart > 0:
        return smart

    log.debug("未知事件[%s]，使用默认选项1", event_name)
    return 1
