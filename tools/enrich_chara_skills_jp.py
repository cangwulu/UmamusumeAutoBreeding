# -*- coding: utf-8 -*-
"""给 chara_skills.json 的每个 card 追加 card_jp（日文形态名）。

来源：tools/.cache/zh_CN.json (JP->CN) 反查 card_name 得到 JP 形态名。
这是**增量增强**：只补充 card_jp 字段，不动其它任何数据，可重复运行。

目的：让 chara_skills 的 card 能直接按「日文规范键」检索，配合 name_resolver
实现「BWIKI 中文形态名 ↔ pretty-derby 中文形态名 ↔ 日文名」三方统一。
"""
import json
import os

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZH = os.path.join(PROJ, "tools", ".cache", "zh_CN.json")
TARGET = os.path.join(PROJ, "resource", "umamusume", "data", "chara_skills.json")


def main():
    zh = json.load(open(ZH, encoding="utf-8"))
    # 只取字符串值，建 CN->JP 反查
    cn2jp = {v: k for k, v in zh.items() if isinstance(v, str)}

    data = json.load(open(TARGET, encoding="utf-8"))
    total_cards = 0
    filled = 0
    for c in data.get("characters", []):
        for card in c.get("cards", []):
            total_cards += 1
            cn = card.get("card_name") or ""
            if "card_jp" not in card and cn:
                jp = cn2jp.get(cn)
                if jp:
                    card["card_jp"] = jp
                    filled += 1
    with open(TARGET, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("卡片总数: %d，本次补 card_jp: %d" % (total_cards, filled))

    # 抽样验证
    for c in data["characters"]:
        if c.get("name") == "无声铃鹿":
            for card in c["cards"]:
                print("  %s -> card_jp=%s" % (card.get("card_name"), card.get("card_jp")))
            break


if __name__ == "__main__":
    main()
