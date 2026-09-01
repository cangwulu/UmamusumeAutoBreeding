"""build_chara_events.py — 从 BWIKI SMW 查询 + 子页抓取角色育成事件。

流程:
1. SMW ask: [[~角色名/*]]|?事件类型  拿每个角色的子页列表
2. 筛"有分支"的子页 (有选项, 无分支的不抓内容)
3. 并发抓子页, 提取 table0(元数据) + table1(选项/效果)
输出: resource/umamusume/data/chara_events.json

用法:
    python tools/build_chara_events.py              # 全量
    python tools/build_chara_events.py --char 特别周  # 单角色
    python tools/build_chara_events.py --include-unbranched  # 连无分支也抓
"""
import os, sys, json, re, time, urllib.request, urllib.parse, html as H
from concurrent.futures import ThreadPoolExecutor, as_completed

WIKI = 'https://wiki.biligame.com/umamusume'
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'resource', 'umamusume', 'data')
CHARA_JSON = os.path.join(DATA_DIR, 'character_bwiki.json')
TARGETS_JSON = os.path.join(DATA_DIR, 'chara_targets.json')
OUT_JSON = os.path.join(DATA_DIR, 'chara_events.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
    'Referer': WIKI,
    'Accept': 'application/json',
}

# character_bwiki name -> BWIKI 真实子页名 (译名差异修正)
NAME_FIX = {
    '东海帝王': '东海帝皇', '富士奇石': '富士奇迹', '春乌菈菈': '春乌拉拉',
    '第一红宝': '第一红宝石', '艾尼风神': '艾尼斯风神', '菱奇宝': '菱钻奇宝',
    '葛城荣主': '葛城王牌', '超级溪流': '超级小海湾', '目白莱恩': '目白赖恩',
    '目白雅丹': '目白阿尔丹', '岛川乔丹': '东瀛佐敦', '阿斯顿真弓': '真弓快车',
    '克里斯象征': '天狼星象征', '重炮': '摩耶重炮',
}


def smw_ask(query: str, timeout: int = 30, retries: int = 3) -> dict:
    """SMW ask 查询, 返回 results dict. 出错返回 {}."""
    url = WIKI + '/api.php?' + urllib.parse.urlencode({
        'action': 'ask', 'query': query, 'format': 'json'
    })
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8'))
            return data.get('query', {}).get('results', {})
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            print(f'  SMW query failed (3 retries): {e}')
            return {}


def fetch_page_html(page: str, timeout: int = 60) -> str:
    url = WIKI + '/api.php?' + urllib.parse.urlencode({
        'action': 'parse', 'page': page, 'prop': 'text', 'format': 'json'
    })
    req = urllib.request.Request(url, headers=HEADERS)
    data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8'))
    if 'parse' not in data:
        return ''
    return data['parse'].get('text', {}).get('*', '')


def list_events(char_name: str, include_unbranched: bool = False):
    """SMW 查某角色的全部事件子页, 返回 [(subpage, event_type), ...]"""
    q = f'[[~{char_name}/*]]|?事件类型|limit=500'
    res = smw_ask(q)
    out = []
    for k, v in res.items():
        et = v.get('printouts', {}).get('事件类型', [])
        et = et[0] if et else ''
        if et == '比赛':
            continue  # 比赛事件不是育成事件
        if not include_unbranched and et != '有分支':
            continue
        out.append((k, et))
    return out


def parse_event_page(html_text: str):
    """解析事件子页: table0=元数据, table1=选项."""
    tabs = list(re.finditer(r'<table[^>]*>', html_text))
    if len(tabs) < 2:
        return None
    meta = {}
    options = []
    for i, m in enumerate(tabs[:3]):
        end = html_text.find('</table>', m.start())
        if end < 0:
            continue
        tab = html_text[m.start():end]
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tab, re.S)
        if not rows:
            continue
        # 第一行是否是表头 (选项/效果)
        first = [H.unescape(re.sub(r'<[^>]+>', '', c)).strip()
                 for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', rows[0], re.S)]
        if first and first[0] in ('选项', '選項'):
            # 选项表
            for r in rows[1:]:
                cells = [H.unescape(re.sub(r'<[^>]+>', '', c)).strip()
                         for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', r, re.S)]
                if len(cells) >= 3:
                    options.append({
                        'option': cells[0],
                        'effect': cells[1],
                        'effect_cn': cells[2] if len(cells) > 2 else '',
                    })
        else:
            # 元数据表
            for r in rows:
                cells = [H.unescape(re.sub(r'<[^>]+>', '', c)).strip()
                         for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', r, re.S)]
                if len(cells) >= 2 and cells[0]:
                    meta[cells[0]] = cells[1]
    return {'meta': meta, 'options': options} if meta or options else None


def fetch_event(subpage: str, retries: int = 3):
    """抓一个事件子页, 返回 (subpage, parsed or None, error). 自动重试."""
    last_err = None
    for attempt in range(retries):
        try:
            html_text = fetch_page_html(subpage)
            if not html_text:
                last_err = 'page not found'
                continue
            parsed = parse_event_page(html_text)
            return subpage, parsed, None
        except Exception as e:
            last_err = str(e)
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
    return subpage, None, last_err


def main():
    args = sys.argv[1:]
    only_char = None
    include_unbranched = False
    if '--char' in args:
        only_char = args[args.index('--char') + 1]
    if '--include-unbranched' in args:
        include_unbranched = True

    d = json.load(open(CHARA_JSON, encoding='utf-8'))
    cs = d['characters']
    # name -> card_names (用 chara_targets 已抓到的 81 个)
    tg = json.load(open(TARGETS_JSON, encoding='utf-8'))
    valid_names = set(c['name'] for c in tg['characters'])
    by_name = {}
    for c in cs:
        if c['name'] in valid_names:
            by_name.setdefault(c['name'], []).append(c['card_name'])

    names = sorted(by_name.keys())
    if only_char:
        names = [n for n in names if only_char in n]

    print(f'[1/3] SMW query {len(names)} characters for event subpages...')
    all_subs = []  # [(char_name, subpage, event_type)]
    query_errors = []
    for i, n in enumerate(names, 1):
        bwiki_name = NAME_FIX.get(n, n)
        try:
            subs = list_events(bwiki_name, include_unbranched)
            for sp, et in subs:
                all_subs.append((n, sp, et))
        except Exception as e:
            query_errors.append((n, str(e)))
            print(f'  {n} query failed: {e}')
        if i % 10 == 0 or i == len(names):
            print(f'  {i}/{len(names)} queried, {len(all_subs)} subpages so far, {len(query_errors)} query errors')
        time.sleep(0.3)

    print(f'[2/3] fetching {len(all_subs)} event subpages (concurrency=8)...')
    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_event, sp): (cn, sp, et) for cn, sp, et in all_subs}
        for i, fut in enumerate(as_completed(futs), 1):
            cn, sp, et = futs[fut]
            subpage, parsed, err = fut.result()
            if err:
                errors[sp] = err
            elif parsed:
                results.setdefault(cn, []).append({
                    'subpage': sp,
                    'event_type': et,
                    'meta': parsed['meta'],
                    'options': parsed['options'],
                })
            if i % 100 == 0 or i == len(all_subs):
                print(f'  {i}/{len(all_subs)} done, {sum(len(v) for v in results.values())} ok, {len(errors)} err')

    # 组装
    out_chars = []
    for n in sorted(by_name.keys()):
        evs = results.get(n, [])
        if not evs:
            continue
        out_chars.append({
            'name': n,
            'card_names': by_name[n],
            'event_count': len(evs),
            'events': evs,
        })

    out = {
        'meta': {
            'source': 'BWIKI:角色子页 (SMW ask 查询 + 子页抓取)',
            'note': '角色育成事件含选项及效果; 仅含"有分支"事件(无分支无选项); 排除"比赛"事件',
            'chara_count': len(out_chars),
            'event_count': sum(c['event_count'] for c in out_chars),
            'errors': errors,
        },
        'characters': out_chars,
    }
    json.dump(out, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[3/3] wrote {OUT_JSON}: {len(out_chars)} chars, {out["meta"]["event_count"]} events')
    if errors:
        print(f'errors: {len(errors)} (sample: {list(errors.items())[:3]})')


if __name__ == '__main__':
    main()
