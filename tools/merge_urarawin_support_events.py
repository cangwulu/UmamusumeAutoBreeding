# -*- coding: utf-8 -*-
"""把 urarawin 协助卡事件（独有部分）并入 event_db.json。

背景（2026-09-03 调查）：
    event_db.json 的 support(协助卡) 事件 371 个（源 pretty-derby db.json），
    urarawin 的协助卡事件去重后 363 个，交集仅 193 —— urarawin 独有 170 个
    触发时只能默认选项 1。本脚本把这 170 个补进 event_db.json。

结构转换：
    urarawin:  {event_name(日文), options: [{option, effect("a\\nb\\nc")}]}
    event_db:  {id, name(中文), name_jp, owner_type:"support", owner_rare,
                owners, choices: [{i, text, text_jp, effects: [a,b,c]}]}
    中文名/选项用 tools/.cache/zh_CN.json 翻译（170 个事件全部可译）。

用法：
    python tools/merge_urarawin_support_events.py
（先备份 event_db.json 为 event_db.json.bak；跑完建议重跑 build_name_index.py）
"""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT_ROOT, "resource", "umamusume", "data")
EVENT_DB = os.path.join(DATA, "event_db.json")
SUPPORT_EVENTS = os.path.join(DATA, "support_events.json")
ZH_CN = os.path.join(PROJECT_ROOT, "tools", ".cache", "zh_CN.json")


def _has_kana(s):
    return any("\u3040" <= c <= "\u30ff" for c in s)


def main():
    # 备份
    if not os.path.isfile(EVENT_DB + ".bak"):
        import shutil
        shutil.copy(EVENT_DB, EVENT_DB + ".bak")
        print("[备份] event_db.json -> event_db.json.bak")

    ed = json.load(open(EVENT_DB, encoding="utf-8"))
    se = json.load(open(SUPPORT_EVENTS, encoding="utf-8"))
    cn_raw = json.load(open(ZH_CN, encoding="utf-8"))
    cn = {k: v for k, v in cn_raw.items() if isinstance(v, str)}

    # 现有 support 事件名_jp 集合
    exist_jp = {e.get("name_jp", "") for e in ed["events"]
                if e.get("owner_type") == "support"}
    print("现有 support 事件:", len(exist_jp))

    # urarawin 独有事件（去重，记录首个出现的卡作为 owners 参考）
    uniq = {}  # name_jp -> {rarity, owners:set, options}
    for c in se["cards"]:
        card_name = c.get("card_name", "")
        rarity = c.get("rarity")
        for e in c.get("events", []):
            nm = (e.get("event_name") or "").strip()
            if not nm or nm in exist_jp:
                continue
            ent = uniq.setdefault(nm, {"rarity": rarity, "owners": set(),
                                       "options": e.get("options", [])})
            # owners: 卡名中文不可得，用日文卡名去 ［］ 前缀后的角色部分
            ent["owners"].add(card_name)

    print("urarawin 独有事件:", len(uniq))

    added = 0
    skipped_no_cn = 0
    new_events = []
    for nm_jp in sorted(uniq):
        ent = uniq[nm_jp]
        nm_cn = cn.get(nm_jp, "")
        if not nm_cn or _has_kana(nm_cn):
            skipped_no_cn += 1
            continue
        choices = []
        for i, o in enumerate(ent["options"] or []):
            opt_jp = (o.get("option") or "").strip()
            opt_cn = cn.get(opt_jp)
            if not opt_cn or _has_kana(opt_cn):
                opt_cn = opt_jp  # 选项保留日文（宁留勿丢）
            # effect 按行拆分（urarawin 用 \n 分隔多条效果）
            raw_effect = (o.get("effect") or "").strip()
            effects = [ln.strip() for ln in raw_effect.split("\n") if ln.strip()]
            choices.append({
                "i": i,
                "text": opt_cn.strip(),
                "text_jp": opt_jp,
                "effects": effects,
            })
        if not choices:
            continue
        # id: 用 name_jp 的稳定散列（event_db 原 id 来自上游，新条目无上游 id）
        import hashlib
        eid = "ur_" + hashlib.md5(nm_jp.encode("utf-8")).hexdigest()[:10]
        owners = sorted(ent["owners"])[:5]
        new_events.append({
            "id": eid,
            "name": nm_cn.strip(),
            "name_jp": nm_jp,
            "owner_type": "support",
            "owner_rare": ent["rarity"],
            "owners": owners,
            "choices": choices,
        })
        added += 1

    # 合并写回（保持原顺序，新事件追加到尾部）
    ed["events"].extend(new_events)
    ed.setdefault("meta", {})
    ed["meta"]["event_count"] = len(ed["events"])          # 总事件数同步
    ed["meta"]["urarawin_support_merged"] = added
    ed["meta"]["support_events_total"] = sum(
        1 for e in ed["events"] if e.get("owner_type") == "support")
    with open(EVENT_DB, "w", encoding="utf-8") as f:
        # 与 build_event_db.py 一致：压缩格式（保持文件体积与 diff 最小）
        json.dump(ed, f, ensure_ascii=False, separators=(",", ":"))

    print("新增 support 事件: %d (中文名缺失跳过: %d)" % (added, skipped_no_cn))
    print("合并后 support 事件总数: %s" % ed["meta"]["support_events_total"])
    print("已写回 %s" % EVENT_DB)


if __name__ == "__main__":
    main()
