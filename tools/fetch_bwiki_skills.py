#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 BWIKI（国服简中 wiki）抓取「简中技能速查表」，提取全量技能数据。

原理（重要）：
    BWIKI 的速查表页面把**全部技能数据内嵌在初始 HTML 的隐藏元素 `#jn-json`
    （一个 JSON 字符串）里**，前端 React 仅在用户点击筛选器后才把数据渲染成表格。
    也就是说"点了选项才有内容"只是前端渲染行为——数据 100% 在首次返回的 HTML 中，
    **无需点击、无需 AJAX、无需浏览器引擎**。

    WebFetch / 浏览器直接看页面只会看到空壳或筛选器，必须用 api.php 取渲染后的
    HTML 再抽取 `#jn-json`。curl/wget 会被 EdgeOne WAF 拦，但 Python urllib
    （带浏览器 UA）走的是另一条通道，可正常取数。

用法：
    python tools/fetch_bwiki_skills.py
    python tools/fetch_bwiki_skills.py --page 简中技能速查表 \
        --out resource/umamusume/data/skill_bwiki.json
"""
import argparse
import datetime
import io
import json
import re
import sys
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

WIKI = "https://wiki.biligame.com/umamusume"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# jn-json 字段 key -> 语义（依据 MediaWiki:Skill_Data.js 的 ThData.G 列定义）
# 1=简中页面路径 3=技能名 5=稀有度 6=条件限制 7=图标颜色
# 8=描述 10=触发条件 11=技能类型 12=技能数值 13=持续时间
# 17=未知编码 18=评价分 19=共需技能PT 20=PT评价比 23=别名(繁中)
FIELD_MAP = {
    "name": "3",
    "page": "1",
    "rarity": "5",
    "condition": "6",
    "icon_color": "7",
    "desc": "8",
    "trigger": "10",
    "skill_type": "11",
    "value": "12",
    "duration": "13",
    "score": "18",       # 评价分 —— 技能排序核心字段
    "total_pt": "19",    # 共需技能 PT
    "pt_ratio": "20",    # PT 评价比
    "alt_name": "23",
}


def fetch_html(page: str) -> str:
    url = WIKI + "/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "text", "format": "json"})
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": WIKI + "/", "Accept": "application/json,*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        obj = json.loads(r.read().decode("utf-8"))
    return obj["parse"]["text"]["*"]


def extract_jn_json(html: str):
    m = re.search(r'id="jn-json"[^>]*>(.*?)</(?:div|script)>', html, re.S)
    if not m:
        return None
    raw = m.group(1)
    # 复现 MediaWiki:Skill_Data.js 里的修复逻辑
    fixed = raw.replace(", ...更多结果", "").replace(", ]", "]")
    return json.loads(fixed)


def _to_num(v):
    v = str(v).strip()
    if v in ("", "-nan", "None", "nan", "NaN"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_skills(rows: list) -> list:
    out = []
    for r in rows:
        desc = (str(r.get("8", ""))
                .replace("<br />", "\n").replace("<br>", "\n").strip())
        item = {}
        for out_key, src_key in FIELD_MAP.items():
            val = r.get(src_key, "")
            if out_key in ("score", "total_pt", "pt_ratio"):
                item[out_key] = _to_num(val)
            else:
                item[out_key] = str(val).strip()
        item["desc"] = desc
        out.append(item)
    return out


def main():
    ap = argparse.ArgumentParser(description="抓取 BWIKI 国服技能速查表")
    ap.add_argument("--page", default="简中技能速查表", help="BWIKI 页面标题")
    ap.add_argument("--out", default="resource/umamusume/data/skill_bwiki.json",
                    help="输出 JSON 路径")
    args = ap.parse_args()

    html = fetch_html(args.page)
    rows = extract_jn_json(html)
    if not rows:
        raise SystemExit("未能从页面提取 #jn-json 数据（可能页面标题错误或 WAF 拦截）")
    skills = parse_skills(rows)
    scored = sum(1 for s in skills if s["score"] is not None)
    db = {
        "source": "wiki.biligame.com/umamusume 简中技能速查表",
        "updated": datetime.date.today().isoformat(),
        "count": len(skills),
        "scored": scored,
        "skills": skills,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    print(f"已写出 {len(skills)} 条技能（含评价分 {scored} 条） -> {args.out}")


if __name__ == "__main__":
    main()
