# -*- coding: utf-8 -*-
"""统一名称解析层：任何「表面名」→ 日文规范键(canonical)。

这是整个项目名字匹配的唯一入口。原先 FuzzyIndex/cosine 散落 chara_skills /
skill_order / stud_planner 等 7 处，阈值还不一致；统一到此处后：
  - 精确别名 → 直出规范键（score=1.0）
  - 否则在「全部别名宇宙」里做 cosine 兜底（阈值 0.5），并强制用 cosine_sim
    复核（绕开 FuzzyIndex 单命中返回「递减阈值」而非真实相似度的坑）
  - 都失败 → (None, 0)

规范键 = 日文名（角色 JP / 形态 JP / 卡 JP / 技能 JP），由 tools/build_name_index.py
从 db.json + zh_CN.json + 各 BWIKI 数据自举生成 resource/umamusume/data/name_index.json。

用法：
    from module.umamusume.name_resolver import get_resolver
    r = get_resolver()
    key, score = r.canonical("无声无瑕")          # -> ("サイレントイノセンス", 1.0)
    key, score = r.canonical("无声铃鹿")          # -> ("サイレンススズカ", 1.0)
    r.resolve("サイレントイノセンス")              # -> "サイレントイノセンス"
"""
import json
import os
import sys
import threading

# 本文件位于 <项目根>/module/umamusume/name_resolver.py，往上 3 层即项目根
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 作为脚本单独运行时 bot 不在 sys.path，把项目根加进去
if os.path.join(_PROJECT_ROOT, "bot") not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from bot.recog.fuzzy_match import cosine_sim

# 本文件位于 <项目根>/module/umamusume/name_resolver.py，往上 3 层即项目根
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAME_INDEX_PATH = os.path.join(_PROJECT_ROOT, "resource", "umamusume", "data", "name_index.json")

_ACCEPT = 0.50  # 模糊兜底接受线（与项目其它模块一致）


class NameResolver(object):
    def __init__(self, path=NAME_INDEX_PATH):
        self.path = path
        self.alias_to_key = {}
        self.by_key = {}
        self._cache = {}          # surface -> (key, score)，避免重复全量 cosine
        self._lock = threading.Lock()
        self.load()

    def load(self):
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.alias_to_key = data.get("alias_to_key", {})
        self.by_key = data.get("by_key", {})
        return self

    def canonical(self, surface, prefer=None):
        """表面名 → (规范键, 置信度)。未命中返回 (None, 0.0)。

        :param prefer: 期望的键类型（"chara"/"form"/"card"/"skill"/"event"/"race"）。
            词面冲突时（同表面名既是角色又是技能，如「一往无前」），alias_to_key
            只存首个键，可能指向错误类型。prefer 传入后：
              - 精确命中但 kind 不符 → 在同 kind 别名池里重找（先精确后 cosine）
              - 仍无 → 返回 (None, 高分) 而非错键
            不传（默认）保持原行为，兼容既有调用。
        """
        if not surface:
            return None, 0.0
        s = surface.strip()
        if not s:
            return None, 0.0
        cache_key = (s, prefer)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        def kind_of(key):
            return self.by_key.get(key, {}).get("kind", "")

        # 1) 精确别名
        if s in self.alias_to_key:
            key = self.alias_to_key[s]
            if prefer is None or kind_of(key) == prefer:
                out = (key, 1.0)
                self._cache[cache_key] = out
                return out
            # kind 不符：在同 kind 别名池里找同表面名（可能有多键挂同别名）
            for k, v in self.by_key.items():
                if v.get("kind") == prefer and s in v.get("aliases", set()):
                    out = (k, 1.0)
                    self._cache[cache_key] = out
                    return out
            # 同 kind 无精确别名 → 落到模糊兜底（下方循环）

        # 2) 模糊兜底：全量 cosine 比对（prefer 时只比同 kind 别名）
        best_key = None
        best_score = 0.0
        if prefer is None:
            for alias in self.alias_to_key:
                sc = cosine_sim(s, alias)
                if sc > best_score:
                    best_score = sc
                    best_key = self.alias_to_key[alias]
        else:
            for k, v in self.by_key.items():
                if v.get("kind") != prefer:
                    continue
                for alias in v.get("aliases", set()):
                    sc = cosine_sim(s, alias)
                    if sc > best_score:
                        best_score = sc
                        best_key = k
        if best_key is None or best_score < _ACCEPT:
            out = (None, best_score)
        else:
            out = (best_key, best_score)
        self._cache[cache_key] = out
        return out

    def resolve(self, surface, prefer=None):
        """便捷函数：只返回规范键（或 None）。"""
        key, _ = self.canonical(surface, prefer=prefer)
        return key

    def kind(self, key):
        """规范键的类型（chara/form/card/skill），未知返回 ''。"""
        if not key:
            return ""
        return self.by_key.get(key, {}).get("kind", "")


_RESOLVER = None
_RES_LOCK = threading.Lock()


def get_resolver(reload=False):
    """进程内单例。"""
    global _RESOLVER
    if _RESOLVER is not None and not reload:
        return _RESOLVER
    with _RES_LOCK:
        if _RESOLVER is None or reload:
            _RESOLVER = NameResolver()
    return _RESOLVER


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    r = get_resolver()
    if len(sys.argv) > 1:
        for a in sys.argv[1:]:
            k, s = r.canonical(a)
            print("%-28s -> %s  (score=%.2f)" % (a, k, s))
    else:
        for a in ["无声无邪", "无声无瑕", "【无声无瑕】无声铃鹿", "无声铃鹿",
                  "サイレントイノセンス", "サイレンススズカ", "#LookatCurren", "无声铃路"]:
            k, s = r.canonical(a)
            print("%-28s -> %s  (score=%.2f)" % (a, k, s))
