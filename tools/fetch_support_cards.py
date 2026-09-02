#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 BWIKI 抓取「简中服（国服）支援卡/协助卡」结构化数据。

产出 resource/umamusume/data/support_card_bwiki.json，字段：
    name   简中卡名（形如「【在耀眼景色的前方】无声铃鹿」）
    chara  关联马娘简中名（形如「无声铃鹿」）
    rarity SSR / SR / R
    type   速度 / 耐力 / 力量 / 根性 / 智力 / 友人 / 团队
    extra  id / 获取方式 / type_raw / jp_name / 固有加成 / 支援效果 / page

## 页面选型（关键，别用错页面）

BWIKI 的支援卡有 3 套平行页面，混用会拿到错服务器的卡名：

    支援卡一览 / 支援卡图鉴        -> 日服（卡名是日文，如「［輝く景色の］サイレンススズカ」）
    繁中支援卡一览 / 繁中支援卡图鉴 -> 繁中服
    简中协助卡一览 / 简中协助卡图鉴 -> 简中服（国服，本脚本目标）

注意国服把「支援卡」叫「协助卡」，所以简中页面名是「简中协助卡*」而不是
「简中支援卡*」（后者是空壳）。页面顶部导航条可确认这一套命名。

## 数据源

1. **简中协助卡图鉴**（主源，服务端直出，最干净）
   页面含 `<table id="CardSelectTr">`，表头为
   `图标 | 卡名 | 关联角色 | 稀有度 | 类型 | 获取方式`。
   MediaWiki 把全部卡片渲染进**同一个 `<tr>`**（行尾无 `</tr>`），
   因此按每 6 个 `<td>` 切一组即可，共 316 组。
   类型字段是**现成文本**，不用从图标/描述猜，覆盖率 100%。

2. **简中协助卡一览**（副源，交叉校验）
   316 个 `<span class="popup">`，每张卡 3 张图：缩略图 / 稀有度 / 类型图标。
   用于交叉校验卡名与类型图标。

3. **支援卡一览**（日服页面，只用于补全 jp_name 与效果）
   553 个 popup，每张卡的 popup 表格含「关联角色 / 固有加成 / 支援效果」。

## 跨服务器关联键

三套页面里卡片的缩略图文件名一致，形如 `Support thumb 30002.png`，
其中 `30002` 是**跨服通用的支援卡 ID**。用它把简中卡名与日服卡名、效果关联。
实测 316 张简中卡全部能在日服页命中（CN-only = 0）。

## 注意

- EdgeOne WAF 只拦浏览器通道；Python urllib 带浏览器 UA 走 api.php 正常返回 200。
- 得意率（数值）BWIKI 未收录，单卡页面（如「简/【在耀眼景色的前方】无声铃鹿」）
  只有 ID 等空模板，取不到，因此置空，不猜。
- 效果名取自日服页面，简中服数值/词条可能随版本调整，仅供参考。

用法：
    python tools/fetch_support_cards.py
    python tools/fetch_support_cards.py --out resource/umamusume/data/support_card_bwiki.json
"""
import argparse
import datetime
import html as html_mod
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

WIKI = "https://wiki.biligame.com/umamusume/api.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 简中服主源（图鉴）与副源（一览）
PAGE_CN_INDEX = "简中协助卡图鉴"
PAGE_CN_LIST = "简中协助卡一览"
# 日服页面，仅用于补全 jp_name / 固有加成 / 支援效果
PAGE_JP_LIST = "支援卡一览"

# BWIKI 用「毅力」表示「根性」；「团队」为国服独有的第 7 类（组队卡）
TYPE_STD = {
    "速度": "速度",
    "耐力": "耐力",
    "力量": "力量",
    "毅力": "根性",
    "智力": "智力",
    "友人": "友人",
    "团队": "团队",
}


def api(**kw) -> dict:
    """调用 BWIKI MediaWiki api.php。"""
    kw.setdefault("format", "json")
    req = urllib.request.Request(
        WIKI + "?" + urllib.parse.urlencode(kw),
        headers={"User-Agent": UA,
                 "Referer": "https://wiki.biligame.com/umamusume/",
                 "Accept": "application/json,*/*"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_html(page: str) -> str:
    return api(action="parse", page=page, prop="text")["parse"]["text"]["*"]


def _text(fragment: str) -> str:
    """去标签 + 反转义 + 压缩空白。"""
    return re.sub(r"\s+", " ", html_mod.unescape(
        re.sub(r"<[^>]+>", "", fragment))).strip()


def parse_cn_index(html: str) -> list:
    """解析「简中协助卡图鉴」的 CardSelectTr 表。

    全部卡片被塞进同一个 <tr>，故按 6 个 <td> 一组切分：
        0 图标(空, 内含 Support thumb <id>.png)
        1 卡名  2 关联角色  3 稀有度  4 类型  5 获取方式
    """
    start = html.find('id="CardSelectTr"')
    if start < 0:
        raise SystemExit("简中协助卡图鉴：未找到 #CardSelectTr 表格")
    end = html.find("</table>", start)
    table = html[start:end]

    raw_cells = re.findall(r"<td[^>]*>(.*?)</td>", table, re.S)
    if len(raw_cells) % 6:
        raise SystemExit(f"简中协助卡图鉴：<td> 数量 {len(raw_cells)} 不是 6 的倍数，"
                         "表格结构可能已变动")
    cells = [_text(c) for c in raw_cells]

    out = []
    for k in range(0, len(cells), 6):
        icon, name, chara, rarity, ctype, acquire = cells[k:k + 6]
        m = re.search(r"Support thumb (\d+)\.png", raw_cells[k])
        out.append({
            "id": m.group(1) if m else "",
            "name": name,
            "chara": chara,
            "rarity": rarity,
            "type_raw": ctype,
            "acquire": acquire,
        })
    return out


def parse_cn_list(html: str) -> dict:
    """解析「简中协助卡一览」：card id -> {name, rarity, type}（来自图标文件名）。"""
    out = {}
    for block in re.findall(r'<span class="popup">.*?</span></span>', html, re.S):
        m_id = re.search(r'alt="Support thumb (\d+)\.png"', block)
        m_title = re.search(r'title="([^"]+)"', block)
        if not (m_id and m_title):
            continue
        title = html_mod.unescape(m_title.group(1))
        if title.startswith("简/"):
            title = title[2:]
        alts = re.findall(r'alt="([^"]+)"', block)
        rarity = next((a[:-4] for a in alts if a in ("SSR.png", "SR.png", "R.png")), "")
        ctype = next((a[:-len("图标.png")] for a in alts if a.endswith("图标.png")), "")
        out[m_id.group(1)] = {"name": title, "rarity": rarity, "type_raw": ctype}
    return out


def parse_jp_list(html: str) -> dict:
    """解析「支援卡一览」（日服）：card id -> {jp_name, chara, 固有加成, 支援效果}。

    popup 内是一张 th/td 交替的表格：关联角色 / 固有加成 / 支援效果(多值)。
    """
    out = {}
    for block in re.findall(r'<span class="popup">.*?</span></span>', html, re.S):
        m_id = re.search(r'alt="Support thumb (\d+)\.png"', block)
        if not m_id:
            continue
        m_title = re.search(r'title="([^"]+)"', block)
        name = html_mod.unescape(m_title.group(1)) if m_title else ""

        # 按文档顺序取 th/td，再根据 th 语义装配
        tokens = [(m.start(), "th", _text(m.group(1)))
                  for m in re.finditer(r"<th[^>]*>(.*?)</th>", block, re.S)]
        tokens += [(m.start(), "td", _text(m.group(1)))
                   for m in re.finditer(r"<td[^>]*>(.*?)</td>", block, re.S)]
        tokens.sort()

        chara = unique = ""
        effects = []
        i = 0
        while i < len(tokens):
            pos, kind, val = tokens[i]
            if kind == "th":
                if val == "关联角色":
                    chara = tokens[i + 1][2] if i + 1 < len(tokens) and tokens[i + 1][1] == "td" else ""
                elif val == "固有加成":
                    unique = tokens[i + 1][2] if i + 1 < len(tokens) and tokens[i + 1][1] == "td" else ""
                elif val == "支援效果":
                    j = i + 1
                    while j < len(tokens) and tokens[j][1] == "td":
                        if tokens[j][2]:
                            effects.append(tokens[j][2])
                        j += 1
                    i = j - 1
            i += 1

        out[m_id.group(1)] = {
            "jp_name": name,
            "chara": chara,
            "unique": unique,
            "effects": effects,
        }
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    ap = argparse.ArgumentParser(description="抓取 BWIKI 简中服支援卡数据")
    ap.add_argument("--out", default=os.path.join(
        root, "resource", "umamusume", "data", "support_card_bwiki.json"),
        help="输出 JSON 路径")
    args = ap.parse_args()

    print(f"[1/3] 抓取 {PAGE_CN_INDEX} ...", flush=True)
    cards = parse_cn_index(fetch_html(PAGE_CN_INDEX))
    print(f"      得到 {len(cards)} 张卡")

    print(f"[2/3] 抓取 {PAGE_CN_LIST}（交叉校验）...", flush=True)
    cn_list = parse_cn_list(fetch_html(PAGE_CN_LIST))
    print(f"      得到 {len(cn_list)} 张卡")

    print(f"[3/3] 抓取 {PAGE_JP_LIST}（补全 jp_name / 效果）...", flush=True)
    jp = parse_jp_list(fetch_html(PAGE_JP_LIST))
    print(f"      得到 {len(jp)} 张卡")

    # 合并：主源为准，副源校验，日服页补全
    warn = []
    merged = []
    for c in cards:
        cid = c["id"]
        ctype_std = TYPE_STD.get(c["type_raw"], "")
        if not ctype_std:
            warn.append(f"未识别类型：{c['name']} -> {c['type_raw']!r}")

        ref = cn_list.get(cid)
        if ref:
            if ref["name"] != c["name"]:
                warn.append(f"卡名不一致 id={cid}：图鉴={c['name']!r} 一览={ref['name']!r}")
            if ref["type_raw"] and ref["type_raw"] != c["type_raw"]:
                warn.append(f"类型不一致 id={cid}：图鉴={c['type_raw']} 一览={ref['type_raw']}")
        else:
            warn.append(f"副源缺失 id={cid}（{c['name']}）")

        j = jp.get(cid, {})
        merged.append({
            "name": c["name"],
            "chara": c["chara"],
            "rarity": c["rarity"],
            "type": ctype_std,
            "jp_name": j.get("jp_name", ""),
            "extra": {
                "id": cid,
                "acquire": c["acquire"],
                "type_raw": c["type_raw"],
                "unique_bonus": j.get("unique", ""),
                "support_effects": j.get("effects", []),
                "jp_chara": j.get("chara", ""),
                "page": "简/" + c["name"],
            },
        })

    typed = sum(1 for m in merged if m["type"])
    db = {
        "meta": {
            "source": [f"BWIKI:{PAGE_CN_INDEX}", f"BWIKI:{PAGE_CN_LIST}",
                       f"BWIKI:{PAGE_JP_LIST}(仅 jp_name/效果)"],
            "count": len(merged),
            "updated": datetime.date.today().isoformat(),
            "type_coverage": f"{typed}/{len(merged)}",
            "note": "type 已把 BWIKI 的「毅力」归一为「根性」；「团队」为国服组队卡。"
                    "得意率为数值字段，BWIKI 未收录，故不产出。",
        },
        "cards": merged,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)

    from collections import Counter
    print(f"\n已写出 {len(merged)} 张卡 -> {args.out}")
    print("  稀有度:", dict(Counter(m["rarity"] for m in merged)))
    print("  类型  :", dict(Counter(m["type"] for m in merged)))
    print(f"  类型覆盖率: {typed}/{len(merged)} "
          f"({typed / len(merged) * 100:.1f}%)" if merged else "  无数据")
    print(f"  jp_name 补全: {sum(1 for m in merged if m['jp_name'])}/{len(merged)}")
    if warn:
        print(f"\n[警告 {len(warn)} 条]")
        for w in warn[:20]:
            print("  -", w)


if __name__ == "__main__":
    main()
