# -*- coding: utf-8 -*-
"""构建统一名称索引 name_index.json（日文名 = 唯一规范键）。

设计：
  - 规范键(canonical) = 日文名。角色级用 charaName 的 JP；形态/卡级用 players[].name 的 JP。
  - 每个规范键聚合所有「中文表面名」：pretty-derby 译名(zh_CN.json)、BWIKI 译名、
    OCR 变体（由下游 resolver 的模糊兜底覆盖，这里只放确定性别名）。
  - 形态级与 BWIKI 形态的对应：先按角色 JP 归组，再按「文件顺序」positional 对齐
    （db.json 形态顺序 ↔ BWIKI 形态顺序），把 BWIKI 形态名挂到对应 db.json JP 形态键。
    顺序或数量不一致时退化为「挂到角色级 JP 键」（仍可用，只是丢形态区分）。

数据源：
  tools/.cache/db.json (players[].name=JP形态, charaName=JP角色)
  tools/.cache/zh_CN.json (JP->CN 译名表)
  resource/umamusume/data/character_bwiki.json
  resource/umamusume/data/support_card_bwiki.json (含 jp_name)
  resource/umamusume/data/skill_db.json (含 name_jp)

产物：resource/umamusume/data/name_index.json
  {
    "version": 1,
    "by_key": { jp_key: {"kind": "chara|form|card|skill", "chara": jp_chara, "aliases": [...]} },
    "alias_to_key": { 表面名: jp_key }
  }
"""
import json
import os
import re
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(PROJ, "tools", ".cache")
DATA = os.path.join(PROJ, "resource", "umamusume", "data")
OUT = os.path.join(DATA, "name_index.json")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _inner_bracket(s):
    """取【…】或 [… ] 内短名；无括号返回原串。"""
    m = re.search(r"[【\[](.*?)[】\]]", s or "")
    return m.group(1).strip() if m else (s or "")


def main():
    zh = _load(os.path.join(CACHE, "zh_CN.json"))
    # JP->CN；过滤掉 dict/list 值，只留字符串映射
    jp2cn = {k: v for k, v in zh.items() if isinstance(v, str)}
    # CN->JP（多个 JP 映射到同一 CN 时取首个）
    cn2jp = {}
    for k, v in jp2cn.items():
        cn2jp.setdefault(v, k)

    db = _load(os.path.join(CACHE, "db.json"))
    cb = _load(os.path.join(DATA, "character_bwiki.json"))
    scb = _load(os.path.join(DATA, "support_card_bwiki.json"))
    sk = _load(os.path.join(DATA, "skill_db.json"))

    by_key = {}        # jp_key -> {kind, chara, aliases:set}
    alias_to_key = {}  # surface -> jp_key

    def add_alias(key, alias, kind=None):
        if not alias:
            return
        a = alias.strip()
        if not a:
            return
        if key not in by_key:
            by_key[key] = {"kind": kind or "form", "chara": "", "aliases": set()}
        by_key[key]["aliases"].add(a)
        # 已映射到其他键则不改（首个胜出，避免冲突覆盖）
        alias_to_key.setdefault(a, key)

    # 1) db.json players：形态级（JP 形态名作键）+ 角色级
    #    同一 charaName 的 players 按出现顺序 = 该角色形态顺序
    db_forms_by_chara = {}
    for p in db.get("players", []):
        jp_form = (p.get("name") or "").strip()
        jp_chara = (p.get("charaName") or p.get("name") or "").strip()
        if not jp_form:
            continue
        cn_form = jp2cn.get(jp_form, jp_form)
        cn_chara = jp2cn.get(jp_chara, jp_chara)
        # 角色级键
        by_key.setdefault(jp_chara, {"kind": "chara", "chara": jp_chara, "aliases": set()})
        by_key[jp_chara]["aliases"].update([jp_chara, cn_chara])
        alias_to_key.setdefault(jp_chara, jp_chara)
        if cn_chara:
            alias_to_key.setdefault(cn_chara, jp_chara)
        # 形态级键
        by_key.setdefault(jp_form, {"kind": "form", "chara": jp_chara, "aliases": set()})
        by_key[jp_form]["chara"] = jp_chara
        by_key[jp_form]["aliases"].update([jp_form, cn_form])
        alias_to_key.setdefault(jp_form, jp_form)
        if cn_form:
            alias_to_key.setdefault(cn_form, jp_form)
        db_forms_by_chara.setdefault(jp_chara, []).append(jp_form)

    # 2) character_bwiki：BWIKI 中文形态名 → 挂到对应 JP 键
    #    按角色归组，做 positional 对齐（BWIKI 顺序 ↔ db.json 顺序）
    bwiki_forms_by_cn_chara = {}
    for c in cb.get("characters", []):
        cn_chara = (c.get("name") or "").strip()
        cn_form_full = (c.get("card_name") or "").strip()
        if not cn_chara or not cn_form_full:
            continue
        bwiki_forms_by_cn_chara.setdefault(cn_chara, []).append(cn_form_full)

    for cn_chara, forms in bwiki_forms_by_cn_chara.items():
        jp_chara = cn2jp.get(cn_chara)
        if not jp_chara or jp_chara not in by_key:
            # 找不到 JP 角色：用 CN 角色名造键（保证可追溯）
            jp_chara = cn_chara
            by_key.setdefault(jp_chara, {"kind": "chara", "chara": jp_chara, "aliases": set()})
        db_forms = db_forms_by_chara.get(jp_chara, [])
        # 角色内 db 形态：CN(译名) -> JP 形态键，用于「按名对齐」（优于纯位置）
        db_form_cn_map = {jp2cn.get(f, f): f for f in db_forms}
        for i, cn_form_full in enumerate(forms):
            inner = _inner_bracket(cn_form_full)
            # 优先按【】内短名 / 全形态名与 db 形态 CN 精确对齐
            # （BWIKI 与 db 可能顺序相反，如 爱丽速子，纯位置会错配）
            if inner in db_form_cn_map:
                form_key = db_form_cn_map[inner]
            elif cn_form_full in db_form_cn_map:
                form_key = db_form_cn_map[cn_form_full]
            else:
                # 名字对不上再退回位置序号；越界则退化为角色级键
                form_key = db_forms[i] if i < len(db_forms) else jp_chara
            add_alias(form_key, cn_form_full)   # 全形态名（含【】+角色名）
            add_alias(form_key, inner)          # 【】内短名
            # 角色级键也挂全形态名（丢失形态区分时仍能落到角色）
            add_alias(jp_chara, cn_form_full)
            add_alias(jp_chara, inner)

    # 3) support_card_bwiki：自带 jp_name（含【】的 JP 形态名）
    for c in scb.get("cards", []):
        jp = (c.get("jp_name") or "").strip()
        cn = (c.get("name") or "").strip()
        if not jp and not cn:
            continue
        key = jp or cn
        by_key.setdefault(key, {"kind": "card", "chara": "", "aliases": set()})
        add_alias(key, jp)
        add_alias(key, cn)
        add_alias(key, _inner_bracket(jp))

    # 4) skill_db：自带 name_jp
    for s in sk.get("skills", []):
        jp = (s.get("name_jp") or "").strip()
        cn = (s.get("name") or "").strip()
        if not jp and not cn:
            continue
        key = jp or cn
        by_key.setdefault(key, {"kind": "skill", "chara": "", "aliases": set()})
        add_alias(key, jp)
        add_alias(key, cn)

    # 5) event_db.json：事件级（name_jp 作规范键）
    #    事件/比赛不在 pretty-derby db.json 体系内，故单独纳入；键用事件自身 JP 名，
    #    别名覆盖 上游CN(name) + 国服CN(event_alias.json 桥接源)。
    ed = _load(os.path.join(DATA, "event_db.json"))
    for ev in ed.get("events", []):
        jp = (ev.get("name_jp") or "").strip()
        cn = (ev.get("name") or "").strip()
        if not jp and not cn:
            continue
        key = jp or cn
        by_key.setdefault(key, {"kind": "event", "chara": "", "aliases": set()})
        add_alias(key, jp, "event")
        add_alias(key, cn, "event")
    # 把 event_alias.json 的国服CN -> 上游CN 桥接源，挂到对应事件键下
    try:
        ea = _load(os.path.join(DATA, "event_alias.json")).get("aliases", {})
        cn2key = {}
        for k, v in by_key.items():
            if v["kind"] == "event":
                for a in v["aliases"]:
                    cn2key.setdefault(a, k)
        for cn_src, cn_tgt in ea.items():
            tgt_key = cn2key.get(cn_tgt)
            if tgt_key:
                add_alias(tgt_key, cn_src, "event")
    except Exception:
        pass

    # 5b) chara_events.json：角色事件「国服简中名」桥接（P4 扩源）
    #     BWIKI 角色子页的每个事件 meta 同时带 简中名 + 事件名(日文)。
    #     event_db 用 name_jp 作规范键；OCR 识别国服简中名。凡日文名已挂
    #     事件键的，把简中名也挂上去 → resolver 国服名→JP 键直接命中。
    #     排除占位（未实装）与空名。
    _JUNK = ("（未实装）", "(未实装)", "未实装", "无选项", "（无）")
    try:
        ce = _load(os.path.join(DATA, "chara_events.json"))
        jp_key_set = {k for k, v in by_key.items() if v["kind"] == "event"}
        bridged = 0
        for c in ce.get("characters", []):
            for ev in c.get("events", []):
                meta = ev.get("meta") or {}
                cn = (meta.get("简中名") or meta.get("中文名") or "").strip()
                jp = (meta.get("事件名") or "").strip()
                if not cn or not jp:
                    continue
                if any(w in cn for w in _JUNK) or cn == "（未实装）":
                    continue
                if jp in jp_key_set:
                    # 该事件的日文名已有规范键 → 简中名挂为别名
                    by_key[jp]["aliases"].add(cn)
                    alias_to_key.setdefault(cn, jp)
                    bridged += 1
        if bridged:
            print("  事件简中名桥接: +%d 别名" % bridged)
    except Exception as exc:
        print("  [warn] chara_events 桥接跳过: %s" % exc)


    # 6) race_bwiki.json：比赛级（jp_name 作规范键）
    #    别名覆盖 国服CN(name) / BWIKI中文(wiki_cn_name) / 台服(tw_name)。
    rb = _load(os.path.join(DATA, "race_bwiki.json"))
    for r in rb.get("races", []):
        jp = (r.get("jp_name") or "").strip()
        name = (r.get("name") or "").strip()
        wiki_cn = (r.get("wiki_cn_name") or "").strip()
        tw = (r.get("tw_name") or "").strip()
        if not jp and not name:
            continue
        key = jp or name
        by_key.setdefault(key, {"kind": "race", "chara": "", "aliases": set()})
        add_alias(key, jp, "race")
        add_alias(key, name, "race")
        add_alias(key, wiki_cn, "race")
        add_alias(key, tw, "race")

    # 序列化：set -> list
    out = {
        "version": 1,
        "by_key": {k: {"kind": v["kind"], "chara": v["chara"], "aliases": sorted(v["aliases"])}
                   for k, v in by_key.items()},
        "alias_to_key": alias_to_key,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # 统计
    kinds = {}
    for v in by_key.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print("已写出 %s" % OUT)
    print("  规范键总数: %d  (按类型: %s)" % (len(by_key), kinds))
    print("  表面名别名总数: %d" % len(alias_to_key))

    # 抽样校验：无声铃鹿两形态应聚到同一角色键，且 BWIKI 形态名可解析到 JP 形态键
    def demo(alias):
        return alias_to_key.get(alias)
    print("\n抽样校验:")
    print("  无声无邪   ->", demo("无声无邪"), "(应为 サイレントイノセンス)")
    print("  无声无瑕   ->", demo("无声无瑕"), "(应为 サイレントイノセンス 或 サイレンススズカ)")
    print("  【无声无瑕】无声铃鹿 ->", demo("【无声无瑕】无声铃鹿"))
    print("  无声铃鹿   ->", demo("无声铃鹿"), "(应为 サイレンススズカ)")
    print("  #LookatCurren ->", demo("#LookatCurren"))
    # 事件/比赛抽样（需数据存在）
    try:
        ed0 = _load(os.path.join(DATA, "event_db.json")).get("events", [])[0]
        if ed0.get("name_jp"):
            print("  %s ->" % ed0.get("name"), demo(ed0.get("name")), "(kind=event)")
    except Exception:
        pass
    try:
        rb0 = _load(os.path.join(DATA, "race_bwiki.json")).get("races", [])[0]
        if rb0.get("jp_name"):
            print("  %s ->" % rb0.get("name"), demo(rb0.get("name")), "(kind=race)")
    except Exception:
        pass


if __name__ == "__main__":
    main()
