#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 BWIKI（国服简中 wiki）抓取「简中巅峰杯事件一览」与「简中赛马娘一览」。

与 fetch_bwiki_skills.py 同源的抓取通道（Python urllib + api.php，绕开 EdgeOne WAF）。
这两页不是 React 前端渲染，而是服务端直出的 HTML 表格，直接解析 <table> 即可。

产物：
    resource/umamusume/data/event_bwiki.json      巅峰杯事件（名称 + 选项 + 效果）
    resource/umamusume/data/character_bwiki.json  赛马娘（马娘名 + 成长率 + 场地/距离/跑法适应性）

用法：
    python tools/fetch_bwiki_extra.py
    python tools/fetch_bwiki_extra.py --no-chars   只抓事件
    python tools/fetch_bwiki_extra.py --no-events  只抓马娘
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

DATA_DIR = "resource/umamusume/data"


def fetch_html(page: str) -> str:
    url = WIKI + "/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "text", "format": "json"})
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": WIKI + "/", "Accept": "application/json,*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        obj = json.loads(r.read().decode("utf-8"))
    return obj["parse"]["text"]["*"]


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&#160;", " ").replace("\u00a0", " ").replace("\n", " ").strip()


def table_rows(tbl: str):
    """把一段 <table> 内容解析成二维列表。"""
    rows = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", tbl, re.S):
        cells = [strip_tags(c) for c in
                 re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(1), re.S)]
        rows.append([c for c in cells if c])
    return rows


# ---------------------------------------------------------------------------
# 事件页
# ---------------------------------------------------------------------------
def parse_events(html: str):
    names = re.findall(r'class="sj-an"><a[^>]*>([^<]+)</a>', html)
    tables = []
    for m in re.finditer(r"<table[^>]*>(.*?)</table>", html, re.S):
        if "选项" in m.group(1):
            tables.append(m.group(1))
    events = []
    for name, tbl in zip(names, tables):
        options = []
        for r in table_rows(tbl):
            if len(r) >= 2 and r[0] not in ("选项", "效果"):
                options.append({"option": r[0], "effect": r[1]})
        events.append({"name": name, "options": options})
    return events


# ---------------------------------------------------------------------------
# 赛马娘页
# ---------------------------------------------------------------------------
def parse_characters(html: str):
    out = []
    blocks = re.split(r'<span class="popup">', html)[1:]
    for b in blocks:
        m = re.search(r"<center><a[^>]*>([^<]+)</a></center>", b)
        card = m.group(1).strip() if m else None
        m = re.search(r"<b>([^<]+)</b><hr", b)
        base = m.group(1).strip() if m else None
        if not base:
            continue

        # 成长率表：<b>之后第一个 wikitable，值行是 5 个百分比 <td>
        growth = {}
        g = re.search(r"<b>" + re.escape(base) + r"</b><hr\s*/?>\s*<table[^>]*>(.*?)</table>", b, re.S)
        if g:
            tds = re.findall(r"<td[^>]*>\s*(\d+%)\s*</td>", g.group(1))
            keys = ["speed", "stamina", "power", "guts", "wisdom"]
            if len(tds) >= 5:
                growth = dict(zip(keys, tds[:5]))

        # 适应性表：class="syx"，逐行解析 类别 + (子项, 等级)
        adapt = {}
        for t in re.finditer(r"<table class=\"syx\"[^>]*>(.*?)</table>", b, re.S):
            tbl = t.group(1)
            for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", tbl, re.S):
                row = tr.group(1)
                cat = re.search(r'class="bt-syx"[^>]*>(.*?)</th>', row, re.S)
                cat = strip_tags(cat.group(1)) if cat else None
                items = re.findall(
                    r'class="bq-syx">([^<]*)<span[^>]*><img alt="([^"]*?)图标', row)
                if cat and items:
                    adapt[cat] = [{"item": strip_tags(i[0]), "grade": i[1]}
                                  for i in items]

        out.append({"card_name": card, "name": base,
                    "growth": growth, "adapt": adapt})
    return out


def dump(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path


def main():
    ap = argparse.ArgumentParser(description="抓取 BWIKI 事件/赛马娘页")
    ap.add_argument("--no-chars", action="store_true")
    ap.add_argument("--no-events", action="store_true")
    args = ap.parse_args()
    today = datetime.date.today().isoformat()

    if not args.no_events:
        html = fetch_html("简中巅峰杯事件一览")
        events = parse_events(html)
        dump({"source": WIKI + " 简中巅峰杯事件一览", "updated": today,
              "count": len(events), "events": events},
             f"{DATA_DIR}/event_bwiki.json")
        print(f"事件：{len(events)} 条 -> {DATA_DIR}/event_bwiki.json")

    if not args.no_chars:
        html = fetch_html("简中赛马娘一览")
        chars = parse_characters(html)
        dump({"source": WIKI + " 简中赛马娘一览", "updated": today,
              "count": len(chars), "characters": chars},
             f"{DATA_DIR}/character_bwiki.json")
        print(f"马娘：{len(chars)} 条 -> {DATA_DIR}/character_bwiki.json")


if __name__ == "__main__":
    main()
