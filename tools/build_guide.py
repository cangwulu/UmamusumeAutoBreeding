"""build_guide.py — 抓取大赛完全攻略两篇, 下载图片, 生成整合图文文档。

输出:
- resource/umamusume/data/guide_imgs/  攻略页全部图片
- docs/guide_tournament.html           整合图文文档 (本地图片, 可离线浏览)

用法:
    python tools/build_guide.py             # 全量 (抓取+下载图+生成文档)
    python tools/build_guide.py --no-fetch  # 跳过抓取, 用已有 cache
"""
import os, sys, json, re, time, urllib.request, urllib.parse, html as H
from concurrent.futures import ThreadPoolExecutor, as_completed

WIKI = 'https://wiki.biligame.com/umamusume'
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TOOLS_DIR, '..'))
CACHE_DIR = os.path.join(TOOLS_DIR, '.cache', 'guide')
IMG_DIR = os.path.join(PROJECT_ROOT, 'resource', 'umamusume', 'data', 'guide_imgs')
OUT_HTML = os.path.join(PROJECT_ROOT, 'docs', 'guide_tournament.html')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
    'Referer': WIKI,
    'Accept': 'text/html,application/json',
}

PAGES = [
    ('赛马娘大赛完全攻略（一）：游戏基础与技能系统', 'guide_1.html', '第一篇 游戏基础与技能系统'),
    ('赛马娘大赛完全攻略（二）：赛道分析与阵容构成', 'guide_2.html', '第二篇 赛道分析与阵容构成'),
]


def fetch_page(page: str, cache_fn: str):
    """抓取并缓存页面 HTML, 返回 HTML 文本."""
    cache_path = os.path.join(CACHE_DIR, cache_fn)
    if os.path.exists(cache_path):
        return open(cache_path, encoding='utf-8').read()
    url = WIKI + '/api.php?' + urllib.parse.urlencode({
        'action': 'parse', 'page': page, 'prop': 'text', 'format': 'json'
    })
    req = urllib.request.Request(url, headers=HEADERS)
    data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))
    t = data['parse']['text']['*']
    os.makedirs(CACHE_DIR, exist_ok=True)
    open(cache_path, 'w', encoding='utf-8').write(t)
    return t


def extract_image_urls(html_text: str):
    """提取所有图片 URL (patchwiki/bilibili 域名)."""
    urls = re.findall(r'src="(https?://[^"]+\.(?:png|jpg|jpeg|gif|webp))"', html_text)
    return sorted(set(urls))


def download_image(url: str, img_dir: str, referer: str = WIKI):
    """下载单张图片, 返回本地文件名 (url hash 命名)."""
    # 用 URL 尾段 + hash 命名, 避免冲突
    tail = url.split('/')[-1]
    # 加 url hash 防止不同 url 同名
    h = str(abs(hash(url)))[:8]
    fn = f"{h}_{tail}"[:80]
    # 清理非法字符
    fn = re.sub(r'[^\w.\-]', '_', fn)
    path = os.path.join(img_dir, fn)
    if os.path.exists(path):
        return fn
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': HEADERS['User-Agent'],
            'Referer': referer,
            'Accept': 'image/*,*/*',
        })
        data = urllib.request.urlopen(req, timeout=30).read()
        with open(path, 'wb') as f:
            f.write(data)
        return fn
    except Exception as e:
        print(f'  img fail {url[:60]}: {e}')
        return None


def localize_images(html_text: str, url_to_local: dict) -> str:
    """把 HTML 里的图片 URL 替换成本地路径."""
    for url, local in url_to_local.items():
        if local:
            html_text = html_text.replace(url, 'guide_imgs/' + local)
    return html_text


def strip_mw_noise(html_text: str) -> str:
    """去掉 MediaWiki 编辑链接/导航等噪音, 保留正文."""
    # 去 edit span
    html_text = re.sub(r'<span class="mw-editsection">.*?</span>', '', html_text, flags=re.S)
    # 去 bread-edit 导航
    html_text = re.sub(r'<div id="bread-edit".*?</div>', '', html_text, flags=re.S)
    # 去目录
    html_text = re.sub(r'<div id="toc"[^>]*>.*?</div>\s*</div>', '', html_text, flags=re.S)
    return html_text


def build_section(page_title: str, display_title: str, html_text: str, url_to_local: dict) -> str:
    """构建单篇整合 HTML section."""
    body = strip_mw_noise(html_text)
    body = localize_images(body, url_to_local)
    # 给图片加 max-width
    body = re.sub(r'<img([^>]*)>', r'<img\1 style="max-width:100%;height:auto;border-radius:6px;">', body)
    return f'''
<section class="guide-part">
  <h1 class="guide-h1">{display_title}</h1>
  <p class="guide-source">来源: <a href="{WIKI}/{urllib.parse.quote(page_title)}" target="_blank">BWIKI - {page_title}</a></p>
  {body}
</section>
'''


def main():
    args = sys.argv[1:]
    fetch = '--no-fetch' not in args

    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)

    print(f'[1/3] fetch & cache {len(PAGES)} guide pages...')
    htmls = []
    for page, cache_fn, display in PAGES:
        if fetch:
            # 强制重抓: 删除 cache
            cache_path = os.path.join(CACHE_DIR, cache_fn)
            if os.path.exists(cache_path):
                os.remove(cache_path)
        t = fetch_page(page, cache_fn)
        htmls.append((page, cache_fn, display, t))
        print(f'  {page}: {len(t)} bytes, {t.count("<img")} imgs')

    print(f'[2/3] download images...')
    all_urls = []
    for _, _, _, t in htmls:
        all_urls.extend(extract_image_urls(t))
    all_urls = sorted(set(all_urls))
    print(f'  total unique urls: {len(all_urls)}')

    url_to_local = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(download_image, u, IMG_DIR): u for u in all_urls}
        for i, fut in enumerate(as_completed(futs), 1):
            u = futs[fut]
            local = fut.result()
            url_to_local[u] = local
            if i % 50 == 0 or i == len(all_urls):
                ok = sum(1 for v in url_to_local.values() if v)
                print(f'  {i}/{len(all_urls)} done, {ok} ok')

    ok = sum(1 for v in url_to_local.values() if v)
    print(f'  downloaded: {ok}/{len(all_urls)}')

    print(f'[3/3] build integrated HTML...')
    sections = []
    for page, _, display, t in htmls:
        sections.append(build_section(page, display, t, url_to_local))

    full_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>赛马娘大赛完全攻略 (整合)</title>
<style>
  :root {{ --bg:#fafafa; --fg:#222; --accent:#3a6ea5; --border:#e0e0e0; }}
  body {{ background:var(--bg); color:var(--fg); font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         line-height:1.7; margin:0; padding:20px; max-width:1100px; margin:0 auto; }}
  .guide-part {{ background:#fff; border:1px solid var(--border); border-radius:8px;
                padding:24px 32px; margin:20px 0; box-shadow:0 1px 3px rgba(0,0,0,0.04); }}
  .guide-h1 {{ color:var(--accent); border-bottom:3px solid var(--accent); padding-bottom:10px; margin-top:0; }}
  .guide-source {{ color:#888; font-size:13px; margin-bottom:20px; }}
  h2 {{ color:var(--accent); border-left:4px solid var(--accent); padding-left:10px; margin-top:32px; }}
  h3 {{ color:#444; margin-top:24px; }}
  table {{ border-collapse:collapse; width:100%; margin:12px 0; }}
  th, td {{ border:1px solid var(--border); padding:6px 10px; text-align:left; }}
  th {{ background:#f0f4f8; }}
  img {{ max-width:100%; height:auto; }}
  a {{ color:var(--accent); }}
  .toc {{ background:#fff; border:1px solid var(--border); border-radius:8px; padding:16px 24px; margin:20px 0; }}
  .toc a {{ text-decoration:none; }}
  .toc ul {{ margin:6px 0; padding-left:24px; }}
  pre, code {{ background:#f5f5f5; padding:2px 6px; border-radius:3px; font-size:13px; }}
  pre {{ padding:10px; overflow-x:auto; }}
</style>
</head>
<body>
<div class="toc">
  <h3 style="margin:0 0 10px;color:var(--accent)">目录</h3>
  <ul>
    <li><a href="#part1">第一篇 游戏基础与技能系统</a></li>
    <li><a href="#part2">第二篇 赛道分析与阵容构成</a></li>
  </ul>
</div>
<section class="guide-part" id="part1">{sections[0]}</section>
<section class="guide-part" id="part2">{sections[1]}</section>
</body>
</html>'''

    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(full_html)
    print(f'wrote {OUT_HTML} ({len(full_html)} bytes)')


if __name__ == '__main__':
    main()
