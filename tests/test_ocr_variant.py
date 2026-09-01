"""
P2 验证：多变体 OCR + 候选文本扩展

运行：
    /e/MINICONDA/envs/uat/python tests/test_ocr_variant.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from bot.recog.ocr_variant import (
    DEFAULT_CONFUSABLE, bottom_option_candidates, event_name_candidates, expand,
    in_range_hsv, tight_bbox, white_ratio,
)

# 真实事件界面截图：凯旋门剧本「你就是最棒的第一！」比赛日对话事件
FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures", "event_sample.png",
)

# 预期文字（人工标注，作为 oracle）
EXPECTED_EVENT_NAME = "养成优俊少女事件"
EXPECTED_OPTION_1 = "你就是最棒的第一！"
EXPECTED_OPTION_2 = "让我们努力争取更厉害的第一吧！"

# 标定 ROI（与 fixtures/event_sample.png 配套使用）
ROI_EVENT = (200, 240, 100, 400)
ROI_OPTION_1 = (690, 740, 80, 660)
ROI_OPTION_2 = (800, 860, 80, 660)


def _has_match(candidates, target):
    """候选列表中是否包含正确结果（允许尾部全角化变体也认作命中）"""
    if not candidates:
        return False
    target_norm = target.replace(" ", "").replace("?", "？").replace("!", "！")
    for c in candidates:
        if c == target or c == target_norm:
            return True
        if target in c or c in target:
            return True
    return False


def _print_candidates(label, cands, expected=None):
    print(f"  {label} ({len(cands)} 候选):")
    hit = _has_match(cands, expected) if expected else None
    for c in cands:
        mark = ""
        if expected and c == expected:
            mark = "  ← 命中"
        elif expected and expected in c:
            mark = "  ← 命中(子串)"
        print(f"     {c!r}{mark}")
    return hit


def test_fixture_exists():
    assert os.path.exists(FIXTURE), f"缺少测试素材: {FIXTURE}"
    print("  [OK] 测试素材就绪")


def test_tight_bbox_invariants():
    """紧包围盒：极端输入不应崩溃"""
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert tight_bbox(empty).size == 0
    solid = np.full((20, 100, 3), 255, dtype=np.uint8)
    # 全白（背景，无文字）→ 触发回退分支，输出仍非空
    out = tight_bbox(solid)
    assert out is not None
    print("  [OK] 紧包围盒鲁棒性")


def test_white_ratio_gate():
    """白字率门控：全黑图 / 全白图都应给出合理值"""
    black = np.zeros((50, 50), dtype=np.uint8)
    white = np.full((50, 50), 255, dtype=np.uint8)
    assert white_ratio(black) == 0.0
    assert abs(white_ratio(white) - 1.0) < 1e-6
    print("  [OK] 白字率门控数值正确")


def test_expand_dedup():
    """错字扩展：把半角标点扩展到全角（OCR 常把 ！认成 !/7）"""
    assert expand("", DEFAULT_CONFUSABLE) == []
    out = expand("你好!", DEFAULT_CONFUSABLE)
    # 原始 '!' → '！' 命中规则，+ 原文本 = 2 项
    assert "你好!" in out
    assert "你好！" in out
    assert len(out) == 2
    out = expand("hello")       # 无任何规则命中
    assert out == ["hello"]
    out = expand("再见!再见?")
    # 每个规则独立应用（不链式，符合 C++ expand 设计）
    assert "再见!再见?" in out        # 原文最后入列
    assert "再见！再见?" in out       # 规则1: '!' → '！'
    assert "再见!再见？" in out       # 规则2: '?' → '？'
    # 不会自动链式 → "再见！再见？" 不会由 expand 产生
    assert "再见！再见？" not in out
    print("  [OK] 错字扩展语义")


def test_event_name_multi_variant():
    """事件名：多变体应至少有一个候选命中"""
    img = cv2.imread(FIXTURE)
    assert img is not None
    cands = event_name_candidates(img, ROI_EVENT)
    assert len(cands) >= 1, "多变体应产生至少 1 个候选"
    hit = _print_candidates("事件名", cands, EXPECTED_EVENT_NAME)
    assert hit, f"多变体候选中无正确结果: {cands}"


def test_bottom_option_multi_variant():
    """选项：多变体应保留正确结果（即使个别变体错字）"""
    img = cv2.imread(FIXTURE)
    c1 = bottom_option_candidates(img, ROI_OPTION_1)
    hit1 = _print_candidates("选项1", c1, EXPECTED_OPTION_1)
    assert hit1, f"选项1 多变体未命中: {c1}"

    c2 = bottom_option_candidates(img, ROI_OPTION_2)
    hit2 = _print_candidates("选项2", c2, EXPECTED_OPTION_2)
    assert hit2, f"选项2 多变体未命中: {c2}"


def test_bottom_option_hsv_gate():
    """HSV 门控：当 HSV mask 白字率过低时，应只走 OTSU/原图，不报异常"""
    img = cv2.imread(FIXTURE)
    # 用一个明显非白色文字区域的 ROI 模拟门控触发
    fake_roi = (0, 5, 0, 5)       # 极小区域，几乎无白字
    cands = bottom_option_candidates(img, fake_roi)
    # 应只跑原图+OTSU（门控触发），结果可能为空但不应异常
    assert isinstance(cands, list)
    print(f"  [OK] HSV 门控 (极小ROI下产出 {len(cands)} 候选，未崩)")


def test_hsv_extraction():
    """HSV 取字：给定颜色范围应返回单通道 mask"""
    yellow = np.zeros((30, 30, 3), dtype=np.uint8)
    yellow[:, :] = (0, 255, 255)  # BGR 黄色 → HSV H=30°
    mask = in_range_hsv(yellow, 25, 35, 100, 255, 100, 255)
    assert mask.shape == (30, 30)
    assert white_ratio(mask) > 0.9
    print("  [OK] HSV 取字 + 白字率组合")


def main():
    print("=" * 66)
    print(" P2 验证：多变体 OCR（移植自 UmaCruise::UmaTextRecognizer）")
    print("=" * 66)

    print("\n[1/3] 工具函数单测")
    test_tight_bbox_invariants()
    test_white_ratio_gate()
    test_expand_dedup()
    test_hsv_extraction()

    print("\n[2/3] 真实事件界面多变体 OCR")
    test_fixture_exists()
    test_event_name_multi_variant()
    test_bottom_option_multi_variant()
    test_bottom_option_hsv_gate()

    print("\n[3/3] P1+P2 端到端冒烟（FuzzyIndex + 多变体候选）")
    from bot.recog.fuzzy_match import FuzzyIndex
    img = cv2.imread(FIXTURE)
    name_cands = event_name_candidates(img, ROI_EVENT)
    opt_cands = bottom_option_candidates(img, ROI_OPTION_2)

    # 用『真实事件名 + 选项文字』做轻量索引，验证检索链路通
    index = FuzzyIndex([EXPECTED_EVENT_NAME, EXPECTED_OPTION_1, EXPECTED_OPTION_2])
    hit_name, score = index.query(name_cands)
    hit_opt, _ = index.query(opt_cands)
    print(f"  事件名检索: {hit_name!r} 得分={score:.2f}")
    print(f"  选项文字检索: {hit_opt!r}")
    assert hit_name == EXPECTED_EVENT_NAME, "端到端：事件名检索失败"
    assert hit_opt == EXPECTED_OPTION_2, "端到端：选项文字检索失败"
    print("  [OK] 端到端：多变体 → FuzzyIndex 命中")

    print("\n" + "=" * 66)
    print(" 全部通过")
    print("=" * 66)


if __name__ == "__main__":
    main()
