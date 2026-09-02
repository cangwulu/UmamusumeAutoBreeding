#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 BWIKI 抓取赛马娘(国服)图片资源并归档到本地。

两类资源：
  1. 马娘头像 (`chara_icon`)：每个角色的各卡面页「Chr icon」图
  2. 协助卡卡面 (`support_card_img`)：每张卡的「Support thumb」卡面立绘

## 数据源与坑（已验证）

- 马娘**没有「角色总览页」**，每个卡面是一独立页面，命名 `简/<卡名>`
  （如 `简/【喜乐无边】东海帝王`）。直接用角色名 `东海帝王` 会 missing；
  但少数角色（如无声铃鹿）有角色名重定向页也能命中。故解析顺序：
      a. `简/` + 该角色第一个 card_name
      b. 角色名 name（处理重定向页）
      c. search(name) 取首个 `简/` 开头结果
- 头像图在角色页 HTML 的 `<img alt="Chr icon <id> <id2> <n>.png">`。
- 协助卡卡面：已有 `support_card_bwiki.json` 每张含 `extra.id`（316/316 全覆盖），
  卡面图文件名 `Support thumb <id>.png`，用 MediaWiki `Special:FilePath` 直链下载。
- EdgeOne WAF 只拦浏览器通道；Python urllib 带 UA 走 api.php / index.php 正常。

## 下载直链

    https://wiki.biligame.com/umamusume/index.php?title=Special:FilePath/<FILE>
  <FILE> 中空格规范化成下划线（MediaWiki 规则），如
    Chr icon 1002 100201 01.png -> Chr_icon_1002_100201_01.png
    Support thumb 30002.png     -> Support_thumb_30002.png
  该 URL 302 到 patchwiki CDN 原图，urllib 自动跟随。

用法：
    python tools/fetch_game_images.py --what all
    python tools/fetch_game_images.py --what chara
    python tools/fetch_game_images.py --what card
    python tools/fetch_game_images.py --what all --workers 10
"""
import argparse
import datetime
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

WIKI_API = "https://wiki.biligame.com/umamusume/api.php"
WIKI_INDEX = "https://wiki.biligame.com/umamusume/index.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "resource", "umamusume", "data")
CHARA_IMG_DIR = os.path.join(ROOT, "resource", "umamusume", "chara_icon")
CARD_IMG_DIR = os.path.join(ROOT, "resource", "umamusume", "support_card_img")


def _req(url: str, binary: bool = False, timeout: int = 120):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": "https://wiki.biligame.com/umamusume/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read() if binary else r.read().decode("utf-8")


def api_get(**kw):
    kw.setdefault("format", "json")
    url = WIKI_API + "?" + urllib.parse.urlencode(kw)
    return json.loads(_req(url))


def safe(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()


def _is_image(data: bytes) -> bool:
    """按文件头判断是否为真实图片（PNG/JPEG），WAF 机器人页/错误页会漏过。"""
    if len(data) < 8:
        return False
    return (data[:8] == b"\x89PNG\r\n\x1a\n") or (data[:3] == b"\xff\xd8\xff") \
        or data[:4] in (b"GIF8", b"RIFF") or data[:4] == b"%PDF"


def download(url: str, path: str, retries: int = 3) -> bool:
    """下载 url 到 path，失败重试。返回是否成功。

    额外拦截 EdgeOne WAF 机器人验证页：它返回 200 + HTML（含 JS 挑战），
    字节数可能不小，但只要不是真实图片就重试。
    """
    for i in range(retries):
        try:
            data = _req(url, binary=True, timeout=120)
            if not _is_image(data):
                raise ValueError("非图片内容(%d bytes)，疑似 WAF 验证页" % len(data))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            if i == retries - 1:
                print("    [下载失败] %s -> %s" % (os.path.basename(path), e))
                return False
            time.sleep(1.5 * (i + 1))


def file_path(name: str) -> str:
    """MediaWiki Special:FilePath 直链（空格->下划线）。"""
    fn = name.replace(" ", "_")
    return WIKI_INDEX + "?title=" + urllib.parse.quote("Special:FilePath/" + fn)


# --------------------------------------------------------------------------
# 马娘头像
# --------------------------------------------------------------------------
def resolve_chara_page(name: str, card_names: list) -> str | None:
    """返回可用的 BWIKI 页面名；全部失败返回 None。"""
    # a. 简/<卡名>
    for cn in card_names:
        if cn:
            page = "简/" + cn
            try:
                api_get(action="parse", page=page, prop="text")
                return page
            except Exception:
                pass
    # b. 角色名（重定向页）
    try:
        api_get(action="parse", page=name, prop="text")
        return name
    except Exception:
        pass
    # c. search 兜底
    try:
        r = api_get(action="query", list="search", srsearch=name, srlimit=5)
        for s in r.get("query", {}).get("search", []):
            t = s["title"]
            if t.startswith("简/") and name in t:
                return t
    except Exception:
        pass
    return None


def fetch_chara_icons(workers: int) -> dict:
    chars = json.load(open(os.path.join(DATA, "character_bwiki.json"), encoding="utf-8"))["characters"]
    by_name = defaultdict(list)
    for c in chars:
        by_name[c["name"]].append(c.get("card_name", ""))

    manifest = {"updated": datetime.date.today().isoformat(), "roles": {}}
    os.makedirs(CHARA_IMG_DIR, exist_ok=True)

    tasks = []  # (name, page, card_names)

    def prep_one(name_cardnames):
        name, cns = name_cardnames
        page = resolve_chara_page(name, cns)
        if not page:
            return name, None, cns
        return name, page, cns

    print("[马娘头像] 解析 %d 个角色页面..." % len(by_name))
    with ThreadPoolExecutor(max_workers=min(workers, 8)) as ex:
        futs = [ex.submit(prep_one, (n, cns)) for n, cns in by_name.items()]
        for f in as_completed(futs):
            name, page, cns = f.result()
            if page:
                tasks.append((name, page, cns))
            else:
                print("  [无页面] %s" % name)

    print("[马娘头像] 开始下载 %d 个角色..." % len(tasks))

    def dl_one(task):
        name, page, cns = task
        try:
            html = api_get(action="parse", page=page, prop="text")["parse"]["text"]["*"]
        except Exception as e:
            return name, [], "页面解析失败: %s" % e
        # 该角色所有卡面页的 Chr icon 都抓（更全面）；主头像取第一张
        # 优先用页面里的 patchwiki CDN 直链（绕开 Special:FilePath 的 WAF 挑战）
        pairs = re.findall(r'alt="(Chr icon [^"]+\.png)"\s+src="([^"]+)"', html)
        if not pairs:  # 兜底：仅 alt，走 Special:FilePath
            pairs = [(f, file_path(f.replace(" ", "_")))
                     for f in sorted(set(re.findall(r'alt="(Chr icon [^"]+\.png)"', html)))]
        saved = []
        base = safe(name)
        idx = 0
        for alt, src in pairs:
            idx += 1
            path = os.path.join(CHARA_IMG_DIR, "%s_%02d.png" % (base, idx))
            if os.path.exists(path) and _is_image(open(path, "rb").read(16)):
                saved.append(path)
                continue
            if download(src, path):
                saved.append(path)
            time.sleep(0.1)
        return name, saved, None

    ok = 0
    pages = {n: p for n, p, _ in tasks}  # 角色名 -> 页面名，供 manifest 记录
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(dl_one, t) for t in tasks]
        for i, f in enumerate(as_completed(futs), 1):
            name, saved, err = f.result()
            if saved:
                ok += 1
                # 主头像复制一份 <name>.png
                if saved:
                    import shutil
                    shutil.copyfile(saved[0], os.path.join(CHARA_IMG_DIR, safe(name) + ".png"))
                manifest["roles"][name] = {
                    "page": pages.get(name),
                    "images": [os.path.relpath(p, ROOT) for p in saved],
                    "avatar": os.path.relpath(saved[0], ROOT),
                }
            else:
                manifest["roles"][name] = {"error": err or "无头像图"}
            if i % 20 == 0 or i == len(tasks):
                print("  进度 %d/%d，成功 %d" % (i, len(tasks), ok))

    manifest["count"] = len(tasks)
    manifest["ok"] = ok
    out = os.path.join(ROOT, "resource", "umamusume", "chara_icon_manifest.json")
    json.dump(manifest, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[马娘头像] 完成：%d/%d 角色有头像 -> %s" % (ok, len(tasks), out))
    return manifest


# --------------------------------------------------------------------------
# 协助卡卡面
# --------------------------------------------------------------------------
def fetch_support_cards(workers: int) -> dict:
    """协助卡卡面：从「简中协助卡图鉴」索引页解析真实 patchwiki CDN 直链下载。

    坑：用 Special:FilePath 直链在并发时会被 EdgeOne WAF 返回机器人验证页
    （200 + HTML，非图片）。而索引页里 img 的 src 直接指向 patchwiki CDN 原图，
    直连 CDN 不经过 WAF，稳定。故这里优先走 CDN 直链。
    """
    db = json.load(open(os.path.join(DATA, "support_card_bwiki.json"), encoding="utf-8"))
    cards = db["cards"]
    os.makedirs(CARD_IMG_DIR, exist_ok=True)

    # 1) 解析索引页：id -> CDN 真实 URL
    print("[协助卡卡面] 解析索引页「简中协助卡图鉴」...")
    cdn = {}
    try:
        html = api_get(action="parse", page="简中协助卡图鉴", prop="text")["parse"]["text"]["*"]
        for cid, src in re.findall(r'alt="Support thumb (\d+)\.png"\s+src="([^"]+)"', html):
            cdn[cid] = src
        print("  索引页命中 %d 张卡面 URL" % len(cdn))
    except Exception as e:
        print("  [警告] 索引页解析失败：%s，退回 Special:FilePath" % e)

    manifest = {"updated": datetime.date.today().isoformat(), "cards": {}}

    def dl_one(card):
        cid = str(card.get("extra", {}).get("id", ""))
        if not cid:
            return card["name"], None, "无 id"
        path = os.path.join(CARD_IMG_DIR, "%s.png" % cid)
        if os.path.exists(path) and _is_image(open(path, "rb").read(16)):
            return card["name"], path, None
        # 优先 CDN 直链；缺失则退回 Special:FilePath
        if download(cdn.get(cid, file_path("Support thumb %s.png" % cid)), path):
            return card["name"], path, None
        return card["name"], None, "下载失败"

    ok = 0
    print("[协助卡卡面] 开始下载 %d 张..." % len(cards))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(dl_one, c) for c in cards]
        for i, f in enumerate(as_completed(futs), 1):
            name, path, err = f.result()
            if path:
                ok += 1
                manifest["cards"][name] = os.path.relpath(path, ROOT)
            else:
                manifest["cards"][name] = {"error": err}
            if i % 50 == 0 or i == len(cards):
                print("  进度 %d/%d，成功 %d" % (i, len(cards), ok))

    manifest["count"] = len(cards)
    manifest["ok"] = ok
    out = os.path.join(ROOT, "resource", "umamusume", "support_card_img_manifest.json")
    json.dump(manifest, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[协助卡卡面] 完成：%d/%d 张 -> %s" % (ok, len(cards), out))
    return manifest


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="抓取 BWIKI 赛马娘图片资源")
    ap.add_argument("--what", choices=["chara", "card", "all"], default="all")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    if args.what in ("chara", "all"):
        fetch_chara_icons(args.workers)
    if args.what in ("card", "all"):
        fetch_support_cards(args.workers)


if __name__ == "__main__":
    main()
