"""
事件库验证：数据质量 + 双路检索端到端

校验 tools/build_event_db.py 的产物是否真的能用，重点回答三个问题：
  1. 数据本身干净吗（无日文残留、选项/效果完整）
  2. bot 里已硬编码的事件名，在新库里检索得到吗
  3. 双路检索（事件名 + 末选项指纹）比单路强多少

运行：
    python tests/test_event_db.py
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module.umamusume.asset.event_db import EventDB, get_event_db

EVENT_DB_PATH = "resource/umamusume/data/event_db.json"

# bot 现有 manifest.py 里硬编码的 5 个事件名
HARDCODED_EVENTS = [
    "安心～针灸师，登☆场",
    "新年的抱负",
    "新年参拜",
    "新年祈福",
    "新手教程",
    "团队成员终于集结完毕!",
]

_CHAR_POOL = []


def _has_kana(s):
    return any("\u3040" <= c <= "\u30ff" for c in s)


def corrupt(text, rng):
    """模拟 OCR 错误：替换 / 删除 / 插入 / 相邻交换"""
    if not text:
        return text
    mode = rng.choice(["sub", "del", "ins", "swap"])
    i = rng.randrange(len(text))
    if mode == "sub":
        return text[:i] + rng.choice(_CHAR_POOL) + text[i + 1:]
    if mode == "del":
        return text[:i] + text[i + 1:]
    if mode == "ins":
        return text[:i] + rng.choice(_CHAR_POOL) + text[i:]
    if mode == "swap" and len(text) >= 2 and i < len(text) - 1:
        return text[:i] + text[i + 1] + text[i] + text[i + 2:]
    return text


# ---------------------------------------------------------------- 1) 数据质量

def test_data_quality(db):
    print("=" * 68)
    print("1) 数据质量")
    print("=" * 68)
    events = db.events
    assert len(events) > 3000, "事件条目过少：%d" % len(events)

    bad_kana = [e for e in events if _has_kana(e["name"])]
    no_choice = [e for e in events if not e.get("choices")]
    with_effect = sum(1 for e in events
                      if any(c.get("effects") for c in e["choices"]))
    cn_choice = sum(1 for e in events
                    for c in e["choices"] if not _has_kana(c["text"]))
    n_choice = sum(len(e["choices"]) for e in events)

    print("  事件条目            %6d" % len(events))
    print("  唯一事件名          %6d" % len({e["name"] for e in events}))
    print("  事件名含日文残留    %6d  (期望 0)" % len(bad_kana))
    print("  无选项的条目        %6d  (期望 0)" % len(no_choice))
    print("  有效果描述的条目    %6d  (%.1f%%)" % (with_effect, with_effect * 100.0 / len(events)))
    print("  选项中文占比        %6d/%d  (%.1f%%)" % (cn_choice, n_choice, cn_choice * 100.0 / n_choice))
    print("  构建时间            %s" % db.meta.get("build_time", "?"))

    assert not bad_kana, "存在未翻译（含假名）的事件名，例如 %r" % bad_kana[:3]
    assert not no_choice, "存在无选项的事件条目"
    assert with_effect * 1.0 / len(events) > 0.9, "有效果描述的事件不足 90%"
    print("  [OK] 数据质量达标\n")


# ---------------------------------------------------------------- 2) 硬编码事件

def test_hardcoded_events(db):
    print("=" * 68)
    print("2) bot 已硬编码事件 → 新库检索")
    print("=" * 68)
    ok = 0
    for name in HARDCODED_EVENTS:
        m = db.search_by_name([name])
        if m:
            ok += 1
            print("  [命中] %-22s score=%.2f via=%s 选项数=%d 同名候选=%d"
                  % (name, m.score, m.via, len(m.choices), len(m.candidates)))
        else:
            print("  [未命中] %-20s" % name)
    print("  ---- %d/%d 命中 ----" % (ok, len(HARDCODED_EVENTS)))
    # 至少四季事件（新年参拜/新年的抱负）应能命中
    assert ok >= 2, "硬编码事件命中过少，检索通路可能有问题"
    print("  [OK] 检索通路正常\n")


# ---------------------------------------------------------------- 3) 双路检索

def test_dual_path(db, sample_size=800, seed=20260901):
    print("=" * 68)
    print("3) 双路检索 vs 单路（模拟 OCR 噪声）")
    print("=" * 68)
    global _CHAR_POOL
    events = db.events
    _CHAR_POOL = sorted({ch for e in events for ch in e["name"]})

    rng = random.Random(seed)
    idxs = rng.sample(range(len(events)), min(sample_size, len(events)))

    rows = []
    for n_err in (1, 2):
        hit_single = 0
        hit_dual = 0
        for i in idxs:
            ev = events[i]
            true_name = ev["name"]
            true_last = ev["choices"][-1]["text"]

            nz_name = true_name
            nz_last = true_last
            for _ in range(n_err):
                nz_name = corrupt(nz_name, rng)
                nz_last = corrupt(nz_last, rng)

            # 单路：只有事件名
            m1 = db.search_by_name([nz_name])
            if m1 and m1.event is ev:
                hit_single += 1
            # 双路：事件名 + 末选项
            m2 = db.search([nz_name], [nz_last])
            if m2 and m2.event is ev:
                hit_dual += 1

        total = len(idxs)
        rows.append((n_err, hit_single * 100.0 / total, hit_dual * 100.0 / total))

    print("  %-14s %12s %12s %10s" % ("噪声强度", "单路(事件名)", "双路(+末选项)", "提升"))
    print("  " + "-" * 52)
    for n_err, s1, s2 in rows:
        print("  %-14s %11.1f%% %11.1f%% %+9.1fpp" % ("%d 处错误" % n_err, s1, s2, s2 - s1))
    print("  " + "-" * 52)
    print("  样本: %d 条事件（未去重，含同名多版本）" % len(idxs))
    print("  说明: 同名事件在库中最多的有 113 个版本，单路必然有歧义\n")

    # 双路不应比单路差
    for _, s1, s2 in rows:
        assert s2 >= s1 - 0.5, "双路检索反而变差：%.1f%% -> %.1f%%" % (s1, s2)
    print("  [OK] 双路检索不低于单路\n")
    return rows


# ---------------------------------------------------------------- 4) 性能

def test_performance(db):
    print("=" * 68)
    print("4) 性能")
    print("=" * 68)
    t0 = time.perf_counter()
    fresh = EventDB(EVENT_DB_PATH).load()
    t_load = time.perf_counter() - t0
    print("  冷加载(含索引构建)  %6.2fs   %d 条事件" % (t_load, len(fresh)))

    t0 = time.perf_counter()
    n = 200
    for i in range(n):
        ev = fresh.events[i * 7 % len(fresh.events)]
        fresh.search([ev["name"]], [ev["choices"][-1]["text"]])
    t_query = (time.perf_counter() - t0) / n
    print("  单次双路查询        %6.2fms" % (t_query * 1000))
    assert t_query < 0.05, "单次查询过慢：%.1fms" % (t_query * 1000)
    print("  [OK] 性能满足育成实时性要求（每次事件决策 < 50ms）\n")


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    if not os.path.isfile(EVENT_DB_PATH):
        print("事件库不存在：%s" % EVENT_DB_PATH)
        print("请先运行：")
        print("    python tools/fetch_upstream.py")
        print("    python tools/build_event_db.py")
        return 1

    db = get_event_db()
    test_data_quality(db)
    test_hardcoded_events(db)
    test_dual_path(db)
    test_performance(db)

    print("=" * 68)
    print("全部通过")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
