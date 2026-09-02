# -*- coding: utf-8 -*-
"""中文育成事件库的运行时访问层。

数据来自 resource/umamusume/data/event_db.json（由 tools/build_event_db.py 构建，
源数据为 pretty-derby/pretty-derby.github.io）。**运行时不联网**。

核心能力是移植自 UmaCruise 的**双路检索**：

    事件名长、带装饰符号，OCR 容易认错；
    而「最后一个选项」短、位置固定、组合唯一 —— 是天然指纹。

        r_opt  = 末选项索引.query(末选项候选)
        r_name = 事件名索引.query(事件名候选)
        if r_opt 命中 and (r_name 未命中 or r_name 得分 < r_opt 得分):
            采用 r_opt
        else:
            采用 r_name

本库上的实测（tools 构建产物，5165 条事件）：
  * 末选项 → 单条事件 唯一映射率 96.8%
  * (事件名, 末选项) 组合唯一定位率 98.1%
即：单靠事件名检索会有歧义（同名事件最多 113 条），加上末选项后基本可唯一定位。

用法：
    from module.umamusume.asset.event_db import get_event_db
    db = get_event_db()
    match = db.search(name_candidates, last_option_candidates)
    if match:
        event = match.event           # dict: name / choices / effects ...
"""

import json
import os
import threading
from collections import defaultdict

from bot.recog.fuzzy_match import cosine_sim

EVENT_DB_PATH = "resource/umamusume/data/event_db.json"
# 国服译名 -> 上游译名的桥接表。上游 zh_CN.json 用繁中/台式译法（例：国服
# 「安心～针灸师，登☆场」对应上游「安〜心笹针师，参☆上」），两者 cosine 仅 0.11，
# 纯模糊匹配跨不过去，只能靠人工维护的别名表兜底。
EVENT_ALIAS_PATH = "resource/umamusume/data/event_alias.json"


class EventMatch(object):
    """一次检索的结果。"""

    __slots__ = ("event", "score", "via", "candidates")

    def __init__(self, event, score, via, candidates):
        self.event = event        # dict，event_db.json 中的一条事件
        self.score = score        # 相似度 0~1
        self.via = via            # "name" | "last_option"
        self.candidates = candidates  # 同一 entry 下的其余候选事件（可能有多条）

    @property
    def name(self):
        return self.event.get("name", "") if self.event else ""

    @property
    def choices(self):
        return self.event.get("choices", []) if self.event else []

    def __repr__(self):
        return "<EventMatch %s score=%.3f via=%s n=%d>" % (
            self.name, self.score, self.via, len(self.candidates))


class EventDB(object):
    """事件库：懒加载 + 双索引 + 双路检索。"""

    def __init__(self, path=EVENT_DB_PATH, alias_path=EVENT_ALIAS_PATH):
        self.path = path
        self.alias_path = alias_path
        self.meta = {}
        self.events = []
        self.aliases = {}                    # 国服译名 -> 上游译名
        self._name_map = defaultdict(list)   # 事件名 -> [event index]
        self._last_map = defaultdict(list)   # 末选项 -> [event index]

    # ------------------------------------------------------------ 加载

    def load(self):
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.meta = data.get("meta", {})
        self.events = data.get("events", [])

        self.aliases = {}
        if os.path.isfile(self.alias_path):
            try:
                with open(self.alias_path, encoding="utf-8") as f:
                    self.aliases = json.load(f).get("aliases", {}) or {}
            except ValueError:
                self.aliases = {}

        self._name_map.clear()
        self._last_map.clear()
        for i, ev in enumerate(self.events):
            self._name_map[ev.get("name", "")].append(i)
            choices = ev.get("choices") or []
            if choices:
                self._last_map[choices[-1].get("text", "")].append(i)

        return self

    def __len__(self):
        if not self.events:
            self.load()
        return len(self.events)

    # ------------------------------------------------------------ 检索

    def _events_of(self, entry, mapping):
        return [self.events[i] for i in mapping.get(entry, ())]

    @staticmethod
    def _best_match(keys, candidates, min_score=0.0):
        """在 keys 池里对多个 OCR 候选暴力 cosine，返回 (best_key, best_score)。

        取代原先的 FuzzyIndex：FuzzyIndex 单命中返回的是「递减阈值」而非真实相似度，
        排序/接受判定不可靠；这里用全量 cosine 取真实最高分（与 affinity/race_bwiki 同款）。
        """
        if not candidates or not keys:
            return None
        best_key, best_score = None, 0.0
        for cand in candidates:
            for k in keys:
                s = cosine_sim(cand, k)
                if s > best_score:
                    best_score = s
                    best_key = k
        if best_key is None or best_score < min_score:
            return None
        return (best_key, best_score)

    def search(self, name_candidates, last_option_candidates=None,
               min_score=0.0):
        """双路检索。

        :param name_candidates:           事件名的多个 OCR 候选（list[str]）
        :param last_option_candidates:    末选项文字的多个 OCR 候选（可选）
        :return: EventMatch 或 None
        """
        if not self.events:
            self.load()
        name_candidates = [c for c in (name_candidates or []) if c]
        last_option_candidates = [c for c in (last_option_candidates or []) if c]
        if not name_candidates and not last_option_candidates:
            return None

        # 国服译名 -> 上游译名，作为额外候选一起参与检索
        if self.aliases:
            extra = []
            for c in name_candidates:
                mapped = self.aliases.get(c)
                if mapped and mapped not in name_candidates:
                    extra.append(mapped)
            name_candidates = name_candidates + extra

        r_name = self._best_match(list(self._name_map.keys()), name_candidates, min_score)
        r_opt = self._best_match(list(self._last_map.keys()), last_option_candidates, min_score)

        # 末选项指纹优先：命中且得分不低于事件名路
        if r_opt and r_opt[0] and (r_name is None or not r_name[0] or r_name[1] < r_opt[1]):
            evs = self._events_of(r_opt[0], self._last_map)
            if evs:
                return EventMatch(evs[0], r_opt[1], "last_option", evs)

        if r_name and r_name[0]:
            evs = self._events_of(r_name[0], self._name_map)
            if evs:
                return EventMatch(evs[0], r_name[1], "name", evs)

        return None

    def search_by_name(self, name_candidates, min_score=0.0):
        """只走事件名一路（末选项 OCR 不可用时的退化路径）。"""
        return self.search(name_candidates, None, min_score)


# ---------------------------------------------------------------- 单例

_DB = None
_LOCK = threading.Lock()


def get_event_db(path=EVENT_DB_PATH, reload=False):
    """获取事件库单例（首次调用时加载，约 0.3s）。"""
    global _DB
    if _DB is not None and not reload:
        return _DB
    with _LOCK:
        if _DB is None or reload:
            if not os.path.isfile(path):
                raise FileNotFoundError(
                    "事件库不存在：%s\n请先运行：python tools/build_event_db.py" % path)
            _DB = EventDB(path).load()
    return _DB
