"""strategy.py — ★优选策略唯一入口（P3）。

职责边界（实现计划-事件库与技能排序.md 第三节）：
    event_db.py    只管「查得到什么」，不管「选哪个」
    event_choice.py 只管「效果怎么解析、单选项怎么打分」（纯工具）
    strategy.py     ★只管「选哪个」——养马策略集中在此，调策略只改这一个文件
    manifest.py     编排：硬编码 → 查库 → 问策略 → 兜底

choose_option 返回：
    int（1-based 选项序号）——直接采纳
    None ——「不决策」，由 manifest 回退到选项 1

当前策略（v1，打分启发式，由 event_choice.score_choice 实现）：
    按当前育成上下文给每个选项打分，取最高分：
      * 属性收益按 expect_attribute 缺口加权（越缺的属性越值钱）
      * 技能提示命中 learn_skill_list 里的目标技能 → 高额加分
      * 干劲/体力/羁绊按经验值折算
    待养马策略（如「优先拉速度/耐力到阈值再补智力」等）总结后，
    只需改动本文件内部实现即可。
"""

try:
    import bot.base.log as logger
    log = logger.get_logger(__name__)
except Exception:                      # 无 colorlog/bot 环境（单测）时用静默兜底
    import logging
    log = logging.getLogger(__name__)
    log.addHandler(logging.NullHandler())


def choose_option(ctx, event_name: str, event: dict):
    """按养马策略从事件记录中选最优选项。

    :param ctx:         育成上下文（含属性/体力/干劲/回合/目标）
    :param event_name:  OCR 识别的事件名（中文，仅作日志用）
    :param event:       event_db 中的事件记录 dict（含 choices[].effects）
    :return: int（1-based 选项序号）或 None（不决策 → 调用方回退选项 1）
    """
    from module.umamusume.script.cultivate_task.event.event_choice import \
        pick_best_choice
    try:
        best = pick_best_choice(ctx, event)
        if best and best > 0:
            return best
    except Exception as exc:
        log.warning("优选策略异常（事件[%s]）：%s，回退由调用方兜底",
                    event_name[:24], exc)
    return None
