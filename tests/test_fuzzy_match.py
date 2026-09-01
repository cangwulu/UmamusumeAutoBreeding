"""
P1 验证：n-gram cosine 匹配引擎

两部分：
  1) 语义单测 —— 校验移植实现与 simstring(C++) 行为一致
  2) 加噪对比 —— 在 3000 条真实中文事件名上，对比 FuzzyIndex 与
     现有 difflib.SequenceMatcher（find_similar_text）的命中率

运行：
    python tests/test_fuzzy_match.py
"""

import os
import random
import sys
import time
from collections import Counter
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.recog.fuzzy_match import (
    FuzzyIndex, cosine_sim, ngram_multiset, ngram_set, normalize, overlap_ratio,
)

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "event_names_cn.txt")


# ---------------------------------------------------------------- 1) 语义单测

def test_ngram_short_string_padding():
    """短于 n 的字符串用 0x01 填充（对齐 ngram.h:74-79）"""
    # "新" 长度1 < n=2 -> src = "新\x01" -> 1 个 gram
    assert ngram_multiset("新", 2) == Counter({"新\x01": 1}), ngram_multiset("新", 2)
    # 长度恰好等于 n -> 不填充
    assert ngram_multiset("新年", 2) == Counter({"新年": 1})
    # 空串 -> 空
    assert ngram_multiset("", 2) == Counter()
    print("  [OK] 短字符串 0x01 填充语义")


def test_ngram_set_numbering():
    """重复 gram 追加序号后缀（对齐 ngram.h:93-100）"""
    assert ngram_set("新新", 1) == ["新", "新2"], ngram_set("新新", 1)
    assert ngram_set("新年", 1) == ["新", "年"]
    # 三次重复 -> 新, 新2, 新3
    assert ngram_set("新新新", 1) == ["新", "新2", "新3"]
    print("  [OK] gram 重复序号后缀语义")


def test_cosine_matches_simstring():
    """cosine = |Q∩S| / sqrt(|Q|*|S|)，多重集交集"""
    # 完全相同 -> 1.0
    assert abs(cosine_sim("新年的抱负", "新年的抱负") - 1.0) < 1e-9
    # 无公共 2-gram -> 0.0
    assert cosine_sim("啊啊啊", "呃呃呃") == 0.0
    # "新年抱负" (g: 新年,年抱,抱负 = 3)
    # "新年的抱负" (g: 新年,年的,的抱,抱负 = 4)
    # 交集 = {新年, 抱负} = 2 ; cos = 2/sqrt(3*4) = 2/3.4641 = 0.5774
    got = cosine_sim("新年抱负", "新年的抱负")
    assert abs(got - 2 / (12 ** 0.5)) < 1e-9, got
    # 对称性
    assert abs(cosine_sim("abc", "abd") - cosine_sim("abd", "abc")) < 1e-12
    print("  [OK] cosine 计算语义 (含多重集交集)")


def test_overlap_ratio_semantics():
    """tiebreak 用「带序号集合」而非多重集（对齐 UmaEventLibrary.cpp:41-64）"""
    # query="新新" -> {"新","新2"} ; cand="新" -> {"新"}
    # match=1, max(2,1)=2 -> 0.5
    assert abs(overlap_ratio("新新", "新") - 0.5) < 1e-9
    # query="新" -> {"新"} ; cand="新新" -> {"新","新2"}
    # "新2" 不在 query 集合中 -> match=1, max(1,2)=2 -> 0.5
    assert abs(overlap_ratio("新", "新新") - 0.5) < 1e-9
    # 完全相同 -> 1.0
    assert abs(overlap_ratio("新年", "新年") - 1.0) < 1e-9
    print("  [OK] 1-gram 裁决语义（非多重集）")


def test_threshold_descending():
    """阈值从高往低降，取第一个能命中的最高阈值"""
    index = FuzzyIndex(["新年的抱负", "新年参拜", "正月"])
    # 精确候选 -> 阈值 1.0 命中
    entry, score = index.query(["新年的抱负"])
    assert entry == "新年的抱负" and abs(score - 1.0) < 1e-9, (entry, score)
    # 加噪候选 -> 阈值降级后命中，score 应 < 1.0
    entry, score = index.query(["新年的抱页"])
    assert entry == "新年的抱负", entry
    assert 0.4 <= score < 1.0, score
    # 完全无关 -> 不命中
    entry, score = index.query(["完全无关的一句话"])
    assert entry is None and score == 0.0, (entry, score)
    print("  [OK] 阈值递减检索语义")


def test_normalize():
    """归一化：去空白 + 转小写，使 OCR 抖动不影响匹配"""
    index = FuzzyIndex(["Re:START！"])
    entry, _ = index.query(["Re: START ！"])
    assert entry == "Re:START！", entry
    print("  [OK] 归一化容错")


# ------------------------------------------------------------ 2) 加噪对比测试

# 常用字池（从语料中取高频字），用于模拟 OCR「认成别的字」
_CHAR_POOL = []


def build_char_pool(names, size=400):
    counter = Counter()
    for n in names:
        counter.update(n)
    return [c for c, _ in counter.most_common(size)]


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


def find_similar_text(target, ref_list, threshold=0):
    """现有实现（bot/recog/ocr.py），用于对照"""
    target = target.replace(" ", "").lower()
    result = ""
    for ref in ref_list:
        s = SequenceMatcher(None, target, ref.replace(" ", "").lower())
        if s.ratio() > threshold:
            result = ref
            threshold = s.ratio()
    return result


def _benchmark_case(name, names, samples, candidates, index):
    """跑一组测试，返回 (命中率, 误匹配率, 未命中率, 耗时)"""
    total = len(samples)

    hit_fuzzy = wrong_fuzzy = 0
    t0 = time.perf_counter()
    for cands, truth in zip(candidates, samples):
        entry, _ = index.query(cands)
        if entry == truth:
            hit_fuzzy += 1
        elif entry is not None:
            wrong_fuzzy += 1
    t_fuzzy = time.perf_counter() - t0

    hit_seq = wrong_seq = 0
    t0 = time.perf_counter()
    for cands, truth in zip(candidates, samples):
        found = ""
        for c in cands:
            found = find_similar_text(c, names, 0.8)
            if found:
                break
        if found == truth:
            hit_seq += 1
        elif found:
            wrong_seq += 1
    t_seq = time.perf_counter() - t0

    print("  %s" % name)
    print("    %-20s 命中 %5.1f%%  误匹配 %5.1f%%  未命中 %5.1f%%  %7.3fs" % (
        "FuzzyIndex", hit_fuzzy / total * 100, wrong_fuzzy / total * 100,
        (total - hit_fuzzy - wrong_fuzzy) / total * 100, t_fuzzy))
    print("    %-20s 命中 %5.1f%%  误匹配 %5.1f%%  未命中 %5.1f%%  %7.3fs" % (
        "SequenceMatcher", hit_seq / total * 100, wrong_seq / total * 100,
        (total - hit_seq - wrong_seq) / total * 100, t_seq))
    print("    %-20s 命中率 %+.1fpp   速度 %.0fx" % (
        "对比", (hit_fuzzy - hit_seq) / total * 100,
        t_seq / t_fuzzy if t_fuzzy else 0))
    print()
    return hit_fuzzy / total


def run_benchmark(sample_size=600, seed=20260901):
    global _CHAR_POOL
    with open(FIXTURE, encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]
    _CHAR_POOL = build_char_pool(names)
    rng = random.Random(seed)
    samples = rng.sample(names, min(sample_size, len(names)))

    print("\n  语料: %d 条真实中文事件名  每组测试样本: %d 条" % (len(names), len(samples)))
    print("  " + "-" * 70)

    t0 = time.perf_counter()
    index = FuzzyIndex(names)
    t_build = time.perf_counter() - t0

    # --- 档位 1：单候选，1 处 OCR 错误（字替换/增删/相邻交换）---
    c1 = [[corrupt(s, rng)] for s in samples]
    r1 = _benchmark_case("[档位1] 单候选 · 1处错误", names, samples, c1, index)

    # --- 档位 2：单候选，2 处 OCR 错误（识别质量差）---
    c2 = []
    for s in samples:
        once = corrupt(s, rng)
        c2.append([corrupt(once, rng) if len(once) >= 2 else once])
    r2 = _benchmark_case("[档位2] 单候选 · 2处错误", names, samples, c2, index)

    # --- 档位 3：多变体候选（3路 OCR，其中1路认对）---
    c3 = []
    for s in samples:
        c3.append([corrupt(s, rng), corrupt(s, rng), s])
    r3 = _benchmark_case("[档位3] 多变体 · 含1路正确", names, samples, c3, index)

    print("  索引构建耗时: %.2fs（整局育成只建一次）" % t_build)
    return r1, r2, r3


def main():
    print("=" * 66)
    print(" P1 验证：n-gram cosine 匹配引擎（移植自 simstring）")
    print("=" * 66)

    print("\n[1/2] 语义单测（对齐 C++ 实现）")
    test_ngram_short_string_padding()
    test_ngram_set_numbering()
    test_cosine_matches_simstring()
    test_overlap_ratio_semantics()
    test_threshold_descending()
    test_normalize()

    print("\n[2/2] 加噪命中率对比")
    run_benchmark()

    print("\n" + "=" * 66)
    print(" 全部通过")
    print("=" * 66)


if __name__ == "__main__":
    main()
