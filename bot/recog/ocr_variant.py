"""
多变体 OCR + 候选文本扩展

移植自 UmaCruise::UmaTextRecognizer（基于 C++ Tesseract + OpenCV），
适配本项目使用的 PaddleOCR（中文 ch 实例）。

核心思路：
  游戏 UI 文字带渐变、描边、花哨背景，OCR 几乎不可能一次识别准。
  UmaCruise 用「同一张图并行多种预处理变体 + 错字扩展」来提升召回率。
  本模块把这一招照搬到 PaddleOCR 上。

三个变体（事件名）：
    原图紧包围盒 / 灰度反色2x放大 / 灰度反色2x放大 + OTSU 二值化

两个变体（选项）：
    灰度反色2x放大 + OTSU / HSV 取字 + 反色（白底黑字）
    前提：白字率 > 5%（白字率门控，否则跳过，避免空识别）

之后对每个变体的 OCR 结果做错字扩展：
    形近字替换 + 全角化 + 原始文本 → 最多 5 个候选

参数默认值严格对齐 UmaTextRecognizer.h：
    kResizeScale = 2.0
    kMinWhiteTextRatioThreshold = 0.05
    紧包围盒膨胀 = 5px，黑带回退 = 10px
    HSV H[12,13] S[75,255] V[100,180]（日服值，国服需 P5 重标）

参考实现：
    UmaUmaCruise-master/UmaCruise/UmaTextRecognizer.cpp:293-373
    UmaUmaCruise-master/UmaCruise/UmaTextRecognizer.h
"""

import cv2
import numpy as np
from typing import Iterable, Optional, Sequence

# 对齐 UmaTextRecognizer.h 常量
K_RESIZE_SCALE = 2.0
K_MIN_WHITE_TEXT_RATIO = 0.05
K_TIGHT_BBOX_DILATE = 5
K_TIGHT_BBOX_FALLBACK = 10

# 日服采样值（国服在 P5 重标）
DEFAULT_HSV = (12, 13, 75, 255, 100, 180)   # H_lo, H_hi, S_lo, S_hi, V_lo, V_hi


# ---------------------------------------------------------------- 图像预处理

def tight_bbox(crop: np.ndarray, dilate: int = K_TIGHT_BBOX_DILATE) -> np.ndarray:
    """紧包围盒：OTSU 二值化找文字边界，外扩 dilate px。

    用意：去掉裁剪后留下的空白边距，让文字尽量占满 ROI，大幅提升 OCR 准确率。
    若全黑/全白找不到连通域，回退到外扩 10px（与 C++ 行为一致）。

    :param crop: ROI 区域 BGR 图像
    :param dilate: 外扩像素数
    :return: 紧包围盒裁剪（仍可能等于原图）
    """
    if crop.size == 0:
        return crop
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(bw)
    if coords is None:
        # 黑带/全空：按回退策略外扩 10px（用 0 填充的较小图也行）
        h, w = gray.shape
        pad = K_TIGHT_BBOX_FALLBACK
        y0, y1 = max(0, pad), max(0, h - pad)
        x0, x1 = max(0, pad), max(0, w - pad)
        y0, y1, x0, x1 = min(y0, h - 1), min(y1, h), min(x0, w - 1), min(x1, w)
        return crop[y0:y1, x0:x1] if y1 > y0 and x1 > x0 else crop
    x, y, w, h = cv2.boundingRect(coords)
    h_total, w_total = crop.shape[:2]
    y0 = max(0, y - dilate)
    y1 = min(h_total, y + h + dilate)
    x0 = max(0, x - dilate)
    x1 = min(w_total, x + w + dilate)
    return crop[y0:y1, x0:x1] if y1 > y0 and x1 > x0 else crop


def _resize_2x(img: np.ndarray) -> np.ndarray:
    """2x 放大（CUBIC），对齐 C++ cv::resize(scale=2.0, INTER_CUBIC)"""
    h, w = img.shape[:2]
    return cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)


def _gray_inverted_2x(crop: np.ndarray) -> np.ndarray:
    """事件名变体 1：灰度 → 反色 → 2x 放大"""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return _resize_2x(255 - gray)


def _otsu_2x(crop: np.ndarray) -> np.ndarray:
    """事件名变体 2：灰度 → 反色 → 2x → OTSU 二值化"""
    return cv2.threshold(_gray_inverted_2x(crop), 0, 255, cv2.THRESH_OTSU)[1]


def white_ratio(img: np.ndarray) -> float:
    """白字率：白像素占比（用于「HSV 提取后是否有文字」门控）"""
    if img.size == 0:
        return 0.0
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float((img > 127).sum()) / img.size


def in_range_hsv(crop: np.ndarray,
                 h_lo: int, h_hi: int, s_lo: int, s_hi: int,
                 v_lo: int, v_hi: int) -> np.ndarray:
    """按 HSV 颜色范围取字（对齐 _InRangeHSVTextColorBounds）"""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (h_lo, s_lo, v_lo), (h_hi, s_hi, v_hi))
    return mask


# ---------------------------------------------------------------- 错字扩展

# 国服常见 OCR 混淆对（占位，P5 阶段会基于真实 OCR 错误样本迭代补充）
DEFAULT_CONFUSABLE = [
    # 标点误识
    ("?", "？"),
    ("!", "！"),
    (",", "，"),
    (".", "。"),
]


def expand(text: str, confusables: Sequence = DEFAULT_CONFUSABLE) -> list:
    """错字扩展：形近字/全角化替换 + 原始文本。

    对齐 UmaTextRecognizer.cpp:547-581 的 expand() 思路（TypoDictionary +
    标点替换 + 原文）。原始文本**最后**入列，因为 retrieve() 阈值递减时会
    先尝试相似度最高的"清洗过"的版本。
    """
    if not text:
        return []
    out = []
    for src, dst in confusables:
        if src in text and src != dst:
            out.append(text.replace(src, dst))
    out.append(text)
    # 去重保序
    seen, dedup = set(), []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup


# ---------------------------------------------------------------- 候选生成（高层 API）

# 全局延迟初始化的 PaddleOCR（与 bot/recog/ocr.py 共享实例）
_OCR_INSTANCE = None


def _get_ocr(lang: str = "ch"):
    """惰性加载 PaddleOCR 实例，与 bot/recog/ocr.py 保持一致。"""
    from bot.recog.ocr import OCR_CH
    return OCR_CH if lang == "ch" else None


def _ocr_line(img: np.ndarray, lang: str = "ch") -> str:
    """单行 OCR：返回识别到的文字。"""
    if img is None or img.size == 0:
        return ""
    ocr = _get_ocr(lang)
    if ocr is None:
        return ""
    res = ocr.ocr(img, cls=False)
    if not res or not res[0]:
        return ""
    return "".join(info[1][0] for info in res[0] if len(info) > 1)


def event_name_candidates(img: np.ndarray, roi: tuple,
                          lang: str = "ch", confusables: Sequence = DEFAULT_CONFUSABLE) -> list:
    """事件名多变体 OCR：3 变体并行（串行实现，PaddleOCR 实例不能并发）→ 错字扩展。

    :param img: 整张截图 BGR
    :param roi: (y0, y1, x0, x1) 或 (y0, y1, x0, x1, h, w) 兼容 (x, y, w, h)
    :return: 所有候选字符串（最多 3 变体 × 5 扩展 = 15 个）
    """
    y0, y1, x0, x1 = roi[:4]
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    tight = tight_bbox(crop)

    variants = [tight, _gray_inverted_2x(tight), _otsu_2x(tight)]
    raw = [_ocr_line(v, lang) for v in variants]
    out = []
    for t in raw:
        out.extend(expand(t, confusables))
    return out


def bottom_option_candidates(img: np.ndarray, roi: tuple,
                             hsv: tuple = DEFAULT_HSV,
                             lang: str = "ch",
                             confusables: Sequence = DEFAULT_CONFUSABLE,
                             min_white_ratio: float = K_MIN_WHITE_TEXT_RATIO) -> list:
    """底部选项 OCR：3 变体（原图 / OTSU / HSV 取字+反色），带白字率门控。

    变体顺序很关键：
      0. 紧包围盒原图 —— 最稳（无处理可能最准）
      1. OTSU 2x 二值化
      2. HSV 取字 + 反色（白底黑字）

    HSV 路径**有门控**：白字率 > min_white_ratio 才进入候选，否则整体跳过，
    避免空图误识别。retrieve() 阈值递减会按列表顺序尝试，所以稳的放前。

    日服 C++ 用白色文字（PaddleOCR 中文场景多为黑字+白底，HSV 参数 P5 校准）。
    """
    y0, y1, x0, x1 = roi[:4]
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    tight = tight_bbox(crop)

    # 变体 0：紧包围盒原图（最稳）
    # 变体 1：OTSU
    thres = _otsu_2x(tight)
    variants = [tight, thres]

    # 变体 2：HSV 取字 + 反色（带门控）
    text_img = in_range_hsv(tight, *hsv)
    if white_ratio(text_img) > min_white_ratio:
        variants.append(255 - text_img)

    raw = [_ocr_line(v, lang) for v in variants]
    out = []
    for t in raw:
        out.extend(expand(t, confusables))
    return out
