"""build_chara_targets.py — 从 BWIKI 角色总页抓育成目标比赛表。

输入: resource/umamusume/data/character_bwiki.json (84 唯一角色名)
输出: resource/umamusume/data/chara_targets.json
       每个角色的目标比赛列表 (年份/月份/前后半/条件/比赛描述/解析字段)

用法:
    python tools/build_chara_targets.py            # 用已有角色名
    python tools/build_chara_targets.py --fetch    # 重新抓取 (默认就是抓取)
    python tools/build_chara_targets.py --char 特别周  # 只抓一个
"""
import os, sys, json, re, time, urllib.request, urllib.parse, html as H
from concurrent.futures import ThreadPoolExecutor, as_completed

WIKI = 'https://wiki.biligame.com/umamusume'
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'resource', 'umamusume', 'data')
CHARA_JSON = os.path.join(DATA_DIR, 'character_bwiki.json')
OUT_JSON = os.path.join(DATA_DIR, 'chara_targets.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
    'Referer': WIKI,
    'Accept': 'application/json',
}


def fetch_page_html(page: str, timeout: int = 60) -> str:
    url = WIKI + '/api.php?' + urllib.parse.urlencode({
        'action': 'parse', 'page': page, 'prop': 'text', 'format': 'json'
    })
    req = urllib.request.Request(url, headers=HEADERS)
    data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8'))
    if 'parse' not in data:
        return ''
    return data['parse']['text']['*']


def find_target_table(html_text: str):
    """定位育成目标比赛表。返回 (rows, table_index) 或 None。"""
    tabs = list(re.finditer(r'<table[^>]*>', html_text))
    for i, m in enumerate(tabs):
        end = html_text.find('</table>', m.start())
        if end < 0:
            continue
        tab = html_text[m.start():end]
        # 目标表的标志: 第一行含 "目标1"
        if re.search(r'目标1[：:]', tab):
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tab, re.S)
            parsed = []
            for r in rows:
                cells = [H.unescape(re.sub(r'<[^>]+>', '', c)).strip()
                         for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', r, re.S)]
                if cells:
                    parsed.append(cells)
            return parsed, i
    return None


def parse_time(s: str):
    """'1年06月 后半' -> {year:1, month:6, half:'后'} ; '2年12月 前半' -> ..."""
    m = re.match(r'\s*(\d+)\s*年\s*(\d+)\s*月\s*(前|后)半', s or '')
    if not m:
        return None
    return {'year': int(m.group(1)), 'month': int(m.group(2)), 'half': m.group(3)}


def parse_fan_need(s: str):
    """'粉丝1000人以上' -> 1000 ; '无' -> None"""
    m = re.search(r'粉丝\s*(\d+)\s*人', s or '')
    return int(m.group(1)) if m else None


def parse_grade_from_desc(desc: str):
    """从比赛描述提取等级: 'G3 京都 草地...' -> 'G3'; '出道战...' -> '出道'"""
    if not desc:
        return ''
    m = re.match(r'\s*(G1|G2|G3|OP|Pre-OP|PreOP|出马|新马|出道|未胜利|条件)', desc)
    if m:
        return m.group(1)
    return ''


def parse_race_desc(desc: str):
    """'G3 京都 草地 英里赛 1800m 右 外 冬' -> dict"""
    if not desc:
        return {}
    parts = [p.strip() for p in desc.split() if p.strip() if p.strip() != '\t']
    out = {'raw': desc, 'grade': '', 'venue': '', 'surface': '', 'distance_class': '',
           'distance': '', 'direction': '', 'inout': '', 'season': '', 'weather': '', 'condition': ''}
    if not parts:
        return out
    out['grade'] = parse_grade_from_desc(desc)
    idx = 0
    if out['grade'] and parts and parts[0].startswith(out['grade']):
        idx = 1
    # venue, surface, distance_class, distance, direction, inout, season, weather, condition
    keys = ['venue', 'surface', 'distance_class', 'distance', 'direction', 'inout', 'season', 'weather', 'condition']
    for k in keys:
        if idx < len(parts):
            out[k] = parts[idx]
            idx += 1
    return out


def parse_targets(rows):
    """4行一组解析目标比赛表。"""
    targets = []
    cur = None
    for cells in rows:
        if not cells:
            continue
        first = cells[0]
        m = re.match(r'目标\s*(\d+)\s*[：:]\s*(.+)', first)
        if m:
            if cur:
                targets.append(cur)
            cur = {
                'index': int(m.group(1)),
                'title': m.group(2).strip(),
                'time_text': '', 'condition': '', 'race_desc': '',
                'time': None, 'fan_need': None, 'race': {},
            }
        elif cur and first in ('时间', '時間'):
            cur['time_text'] = cells[1] if len(cells) > 1 else ''
            cur['time'] = parse_time(cur['time_text'])
        elif cur and first in ('条件',):
            cur['condition'] = cells[1] if len(cells) > 1 else ''
            cur['fan_need'] = parse_fan_need(cur['condition'])
        elif cur and first in ('比赛描述', 'レース情報', '比赛信息'):
            cur['race_desc'] = cells[1] if len(cells) > 1 else ''
            cur['race'] = parse_race_desc(cur['race_desc'])
    if cur:
        targets.append(cur)
    return targets


def fetch_one(name: str):
    """抓一个角色总页, 返回 (name, targets or None, error or None)"""
    try:
        html_text = fetch_page_html(name)
        if not html_text:
            return name, None, 'page not found'
        found = find_target_table(html_text)
        if not found:
            return name, None, 'no target table'
        rows, _ = found
        targets = parse_targets(rows)
        return name, targets, None
    except Exception as e:
        return name, None, str(e)


def main():
    args = sys.argv[1:]
    only_char = None
    if '--char' in args:
        i = args.index('--char')
        only_char = args[i + 1]

    d = json.load(open(CHARA_JSON, encoding='utf-8'))
    cs = d['characters'] if isinstance(d, dict) and 'characters' in d else d
    # name -> [card_names]
    by_name = {}
    for c in cs:
        by_name.setdefault(c['name'], []).append(c['card_name'])

    names = sorted(by_name.keys())
    if only_char:
        names = [n for n in names if only_char in n]

    print(f'fetching {len(names)} character pages...')
    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_one, n): n for n in names}
        for i, fut in enumerate(as_completed(futs), 1):
            name, targets, err = fut.result()
            if err:
                errors[name] = err
            else:
                results[name] = targets
            if i % 10 == 0 or i == len(names):
                print(f'  {i}/{len(names)} done, {len(results)} ok, {len(errors)} err')

    # 组装
    out_chars = []
    for name in sorted(by_name.keys()):
        if name not in results:
            continue
        out_chars.append({
            'name': name,
            'card_names': by_name[name],
            'targets': results[name],
        })

    out = {
        'meta': {
            'source': 'BWIKI:角色总页 (育成目标比赛表)',
            'note': '每个角色的目标比赛列表, 含时间/粉丝门槛/比赛描述; 多形态共享同一套目标',
            'chara_count': len(out_chars),
            'target_count': sum(len(c['targets']) for c in out_chars),
            'errors': errors,
        },
        'characters': out_chars,
    }
    json.dump(out, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'wrote {OUT_JSON}: {len(out_chars)} chars, {out["meta"]["target_count"]} targets')
    if errors:
        print(f'errors: {errors}')


if __name__ == '__main__':
    main()
