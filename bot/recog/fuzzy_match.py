"""
n-gram cosine 模糊匹配引擎

精确移植自 UmaCruise 内置的 simstring（C++）检索语义，用于替代
`difflib.SequenceMatcher` 做 OCR 文本的容错匹配。

相比 SequenceMatcher 的优势：
1. 基于 n-gram 倒排索引，对「多字 / 少字 / 形近字」的容忍度显著更高；
2. 支持**多候选 + 阈值递减**：从 1.0 逐级降到下限，取第一个能命中的最高阈值，
   天然做到「高置信优先、逐级降级」，比固定阈值稳；
3. 预计算 + 倒排剪枝，单次查询在万级条目下仍是毫秒级，索引可整局复用。

参考实现：
    UmaUmaCruise-master/UmaCruise/simstring/ngram.h、measure.h
    UmaUmaCruise-master/UmaCruise/UmaEventLibrary.cpp:20-99 (retrieve)
"""

import math
from collections import Counter
from typing import Iterable, Optional, Sequence

# simstring::ngrams 使用 0x01 作为短字符串填充标记
_PAD = "\x01"

# 默认阈值参数，对齐 UmaEventLibrary.h / UmaLibrary/Common.json
DEFAULT_START_THRESHOLD = 1.0
DEFAULT_MIN_THRESHOLD = 0.4
DEFAULT_STEP = 0.05
# 事件名 / 选项 DB 用 2-gram（马娘名 DB 用 3-gram，参见 UmaEventLibrary.cpp）
DEFAULT_NGRAM = 2


def normalize(text: str) -> str:
    """归一化：去除所有空白字符并转小写。

    对齐既有 find_similar_text 的行为（去空格 + lower），
    使 OCR 结果中的空格/大小写抖动不影响匹配。
    """
    return "".join(text.split()).lower()


def ngram_multiset(text: str, n: int) -> Counter:
    """simstring ngram_generator(n, be=False) 的多重集等价形式。

    注意与 C++ 实现对齐的关键点：**短于 n 的字符串用 0x01 填充至长度 n**。
    若不填充，单字（如「！」）将生成空 gram 集合，永远无法被检索到。
    """
    if not text:
        return Counter()
    src = text + _PAD * (n - len(text)) if len(text) < n else text
    return Counter(src[i:i + n] for i in range(len(src) - n + 1))


def ngram_set(text: str, n: int) -> list:
    """simstring ngram_generator 的**原始输出**：重复 gram 追加序号后缀。

    例（n=1）："新新" -> ["新", "新2"]

    这与「多重集」语义**不等价** —— 只有相同序号的重复项才会互相匹配。
    仅 tiebreak 裁决需要这份精确语义（见 UmaEventLibrary.cpp:41-64），
    cosine 计算用 ngram_multiset 即可（两者在 cosine 下等价）。
    """
    if not text:
        return []
    src = text + _PAD * (n - len(text)) if len(text) < n else text
    seen: Counter = Counter()
    out = []
    for i in range(len(src) - n + 1):
        gram = src[i:i + n]
        seen[gram] += 1
        out.append(gram if seen[gram] == 1 else "%s%d" % (gram, seen[gram]))
    return out


def _cosine(cq: Counter, cs: Counter) -> float:
    """simstring::cosine = |Q∩S| / sqrt(|Q| * |S|)，多重集交集"""
    inter = sum((cq & cs).values())
    if not inter:
        return 0.0
    return inter / math.sqrt(sum(cq.values()) * sum(cs.values()))


def cosine_sim(query: str, cand: str, n: int = DEFAULT_NGRAM) -> float:
    """计算两个字符串的 n-gram cosine 相似度"""
    return _cosine(ngram_multiset(query, n), ngram_multiset(cand, n))


def overlap_ratio(query: str, cand: str) -> float:
    """多结果裁决用的 1-gram 重叠率（对齐 retrieve() 中 xstrs.size() >= 2 分支）。

    语义：cand 的每个 gram，只要**作为带序号元素**出现在 query 的 gram 集合中就 +1，
    再除以 max(|query|, |cand|)。
    """
    qg = ngram_set(query, 1)
    cg = ngram_set(cand, 1)
    if not qg or not cg:
        return 0.0
    qset = set(qg)
    match = sum(1 for gram in cg if gram in qset)
    return match / max(len(qg), len(cg))


class FuzzyIndex:
    """n-gram cosine 倒排索引，检索语义对齐 simstring::reader::retrieve

    典型用法：
        index = FuzzyIndex(event_name_list)          # 建一次，整局复用
        entry, score = index.query(ocr_candidates)    # 候选可有多个
        if entry is not None:
            ...
    """

    def __init__(self, entries: Iterable[str], n: int = DEFAULT_NGRAM,
                 normalize_text: bool = True):
        """
        :param entries: 待检索的文本集合（如事件名列表）
        :param n: n-gram 长度，事件名/选项用 2，马娘名用 3
        :param normalize_text: 是否对文本做归一化（去空白 + 转小写）
        """
        self.n = n
        self.normalize_text = normalize_text

        self.entries: list = []          # 原始文本（返回给用户）
        self._keys: list = []            # 归一化后的检索键
        self._grams: list = []           # 每条目的 gram 多重集
        self._sizes: list = []           # 每条目的 gram 总数
        self._inv: dict = {}             # 倒排索引：gram -> [entry_idx]

        for entry in entries:
            key = normalize(entry) if normalize_text else entry
            if not key:
                continue
            idx = len(self.entries)
            self.entries.append(entry)
            self._keys.append(key)
            grams = ngram_multiset(key, n)
            self._grams.append(grams)
            self._sizes.append(sum(grams.values()))
            for gram in grams:
                bucket = self._inv.get(gram)
                if bucket is None:
                    self._inv[gram] = [idx]
                else:
                    bucket.append(idx)

    def __len__(self) -> int:
        return len(self.entries)

    def query(self, candidates: Sequence[str],
              start: float = DEFAULT_START_THRESHOLD,
              min_threshold: float = DEFAULT_MIN_THRESHOLD,
              step: float = DEFAULT_STEP) -> tuple:
        """阈值递减 + 多候选检索，返回 (命中的原始文本, 得分) 或 (None, 0.0)。

        算法（对齐 UmaEventLibrary.cpp:20-99）：
            for threshold from start down to min_threshold by step:
                for query in candidates:            # 多变体 OCR 产生的候选
                    hits = 检索(相似度 >= threshold)
                    if hits: 记录 query 并跳出候选循环
                if hits: 跳出阈值循环
            if 命中 >= 2 个: 用 1-gram 重叠率裁决，取最高
            if 命中 1 个  : 直接返回 (文本, 当前阈值)
            else          : 返回 (None, 0.0)

        「取第一个能命中的最高阈值」使高置信结果优先，避免低阈值下的误匹配。
        """
        if not self.entries or not candidates:
            return None, 0.0

        # 用整数步进避免浮点累加误差（0.1 连减会漂移）
        n_steps = int(math.floor((start - min_threshold) / step + 1e-9)) if step > 0 else 0

        for k in range(n_steps + 1):
            threshold = start - k * step
            for candidate in candidates:
                key = normalize(candidate) if self.normalize_text else candidate
                if not key:
                    continue
                hits = self._filter(key, threshold)
                if not hits:
                    continue
                if len(hits) >= 2:
                    # 多个候选 → 1-gram 重叠率裁决
                    best = max(hits, key=lambda e: overlap_ratio(
                        key, normalize(e) if self.normalize_text else e))
                    return best, overlap_ratio(
                        key, normalize(best) if self.normalize_text else best)
                return hits[0], threshold

        return None, 0.0

    def query_all(self, query: str, threshold: float = DEFAULT_MIN_THRESHOLD) -> list:
        """返回所有相似度 >= threshold 的条目（不做阈值递减，用于调试/兜底）"""
        key = normalize(query) if self.normalize_text else query
        return self._filter(key, threshold) if key else []

    def _filter(self, key: str, threshold: float) -> list:
        """检索相似度 >= threshold 的条目（已去重）"""
        cq = ngram_multiset(key, self.n)
        qn = sum(cq.values())
        if qn == 0:
            return []

        # simstring::cosine 的 size 剪枝：
        #   min_size(q, a) = ceil(a^2 * q) <= |s| <= floor(q / a^2) = max_size(q, a)
        lo = math.ceil(threshold * threshold * qn)
        hi = math.floor(qn / (threshold * threshold)) if threshold > 0 else math.inf

        # 倒排剪枝：只检查与 query 有公共 gram 的条目
        cand_idx = set()
        for gram in cq:
            bucket = self._inv.get(gram)
            if bucket:
                cand_idx.update(bucket)

        out, seen = [], set()
        for idx in cand_idx:
            size = self._sizes[idx]
            if size < lo or size > hi:
                continue
            inter = sum((cq & self._grams[idx]).values())
            if not inter:
                continue
            if inter / math.sqrt(qn * size) >= threshold:
                entry = self.entries[idx]
                if entry not in seen:      # 同名条目只算一个，避免误判为"多命中"
                    seen.add(entry)
                    out.append(entry)
        return out
