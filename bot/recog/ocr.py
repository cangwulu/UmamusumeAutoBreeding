import cv2
import os
import re
import paddleocr
from difflib import SequenceMatcher
import bot.base.log as logger
import time

log = logger.get_logger(__name__)

# Paddle 推理引擎在 Windows 下无法打开含中文等非 ASCII 字符的路径
# (例如 C:\Users\路遥\.paddleocr\... 会报 "Cannot open file .../inference.pdmodel")，
# 因此把 OCR 模型固定存放在项目内纯英文路径下，避免放到用户目录(~/.paddleocr)中。
_MODEL_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "models", "paddleocr")

OCR_JP = paddleocr.PaddleOCR(
    lang="japan",
    show_log=False,
    use_angle_cls=False,
    det_model_dir=os.path.join(_MODEL_ROOT, "det", "ml"),
    rec_model_dir=os.path.join(_MODEL_ROOT, "rec", "japan"),
    cls_model_dir=os.path.join(_MODEL_ROOT, "cls"),
)
OCR_CH = paddleocr.PaddleOCR(
    lang="ch",
    show_log=False,
    use_angle_cls=False,
    det_model_dir=os.path.join(_MODEL_ROOT, "det", "ch"),
    rec_model_dir=os.path.join(_MODEL_ROOT, "rec", "ch"),
    cls_model_dir=os.path.join(_MODEL_ROOT, "cls"),
)
OCR_EN = paddleocr.PaddleOCR(
    lang="en",
    show_log=False,
    use_angle_cls=False,
    det_model_dir=os.path.join(_MODEL_ROOT, "det", "en"),
    rec_model_dir=os.path.join(_MODEL_ROOT, "rec", "en"),
    cls_model_dir=os.path.join(_MODEL_ROOT, "cls"),
)

# ocr 文字识别图片
def ocr(img, lang="ch"):
    if lang == "ch":
        return OCR_CH.ocr(img, cls=False)
    if lang == "japan":
        return OCR_JP.ocr(img, cls=False)


# ocr_line 文字识别图片，返回所有出现的文字
def ocr_line(img, lang="ch"):
    ocr_result = ocr(img, lang)
    text = ""
    ocr_result = ocr_result[0]
    for text_info in ocr_result:
        if len(text_info) > 0:
            text += text_info[1][0]
    return text

# 剔除所有符号, 只保留中文字符, 英文字符, 数字
def extract_chinese_english_digits(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", text)

# ocr_digits 限制只识别数字，可以提升数字识别的准确度
def ocr_digits(img):
    res = OCR_EN.ocr(img, cls=False)[0]
    # 提取所有识别结果，按置信度从高到低排序
    digits = [(info[1][0], info[1][1]) for info in res]
    if not digits:
        return ""
    # 选置信度最高的那一项
    best, _ = max(digits, key=lambda x: x[1])
    return best

# find_text_pos 查找目标文字在图片中的位置
def find_text_pos(ocr_result, target):
    threshold = 0.6
    result = None
    for text_info in ocr_result:
        if len(text_info) > 0:
            s = SequenceMatcher(None, target, text_info[0][1][0])
            if s.ratio() > threshold:
                result = text_info[0]
                threshold = s.ratio()
    return result


def find_similar_text(target_text: str, ref_text_list: list[str], threshold=0):
    # 去除所有空格, 并把英文字符转为小写
    target_text = target_text.replace(" ", "").lower()
    result = ""
    for ref_text in ref_text_list:
        s = SequenceMatcher(None, target_text, ref_text.replace(" ", "").lower())
        if s.ratio() > threshold:
            result = ref_text
            threshold = s.ratio()
    return result
