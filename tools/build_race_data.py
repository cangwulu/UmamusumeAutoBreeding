# -*- coding: utf-8 -*-
"""构建 race_bwiki.json —— BWIKI 比赛数据资产（简中服权威译名）。

数据源（api.php 抓取，绕过 EdgeOne WAF）：
- 比赛 (race_jp)：日服表，313 场。含 名称(日文)/中文名/繁译名/时间/等级/地点/场地/
  长度/赛程/方向/奖励粉丝/所需粉丝/成绩点/商店币/备注/属性
- 简中比赛 (race_cn)：简中服表，281 场。仅 名称/时间/奖励粉丝/所需粉丝/备注/属性 有值，
  其余列空 —— **译名以此表为准**

关联键：行图标文件名中的 race_id（日服 `Thum race rt 000 XXXX`，简中 `Jian thum race
rt 000 XXXX`）。两表 race_id 完全一致（已验证：281 个简中 id 全部落在 313 个日服 id 内，
时间表与属性加成零差异，仅译名不同）。

另附 race.csv（项目原有 376 行）→ bwiki race_id 映射，按 名字 → csv_id 反向挂接。

用法：
  python tools/build_race_data.py            # 使用 tools/.cache 缓存
  python tools/build_race_data.py --fetch    # 重新抓取
"""
import argparse
import csv
import html as HTML
import json
import os
import re
import urllib.parse
import urllib.request

WIKI = 'https://wiki.biligame.com/umamusume'
CACHE = 'tools/.cache'
OUT = 'resource/umamusume/data/race_bwiki.json'
RACE_CSV = 'resource/umamusume/data/race.csv'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
    'Referer': WIKI,
    'Accept': 'application/json',
}

# 场地/赛道译名（日服表用日文，统一转简中）
VENUE_MAP = {
    '東京': '东京', '中山': '中山', '中京': '中京', '京都': '京都', '阪神': '阪神',
    '新潟': '新潟', '札幌': '札幌', '函館': '函馆', '小倉': '小仓', '福島': '福岛',
    '大井': '大井', '松浪': '松浪',
}
TRACK_MAP = {'芝': '草地', 'ダート': '泥地', '草地': '草地', '泥地': '泥地'}
# 备注直译（简中表备注为空时兜底）
NOTE_MAP = {
    '春ダート': '春泥地赛', '秋ダート': '秋泥地赛', '春秋ダート': '春秋泥地赛',
    '春スプリント': '春短距离赛', '秋スプリント': '秋短距离赛',
    '春秋スプリント': '春秋短距离赛',
    '春マイル': '春英里赛', '秋マイル': '秋英里赛', '春秋マイル': '春秋英里赛',
    '春シニア三冠': '春季高级三冠', '秋シニア三冠': '秋季高级三冠',
    '春秋シニア三冠': '春秋季高级三冠',
    '春中長距離': '春中长距离', '秋中長距離': '秋中长距离', '春秋中長距離': '春秋中长距离',
    '春クラシック三冠': '春季经典三冠',
}


def fetch_page(page, cache_file):
    path = os.path.join(CACHE, cache_file)
    if os.path.isfile(path) and os.path.getsize(path) > 10000:
        return open(path, encoding='utf-8').read()
    url = WIKI + '/api.php?' + urllib.parse.urlencode(
        {'action': 'parse', 'page': page, 'prop': 'text', 'format': 'json'})
    req = urllib.request.Request(url, headers=dict(
        HEADERS, Referer=WIKI + '/' + urllib.parse.quote(page)))
    data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))
    t = data['parse']['text']['*']
    os.makedirs(CACHE, exist_ok=True)
    open(path, 'w', encoding='utf-8').write(t)
    return t


def parse_table(html_text, id_pattern):
    """解析主数据表，返回 {race_id: (cells, img_src)}。"""
    tabs = list(re.finditer(r'<table[^>]*>', html_text))
    m2 = tabs[1]
    end = html_text.find('</table>', m2.start())
    tab = html_text[m2.start():end]
    out = {}
    for rm in re.finditer(r'<tr[^>]*>(.*?)</tr>', tab, re.S):
        body = rm.group(1)
        cells = [HTML.unescape(re.sub(r'<[^>]+>', '', c)).strip()
                 for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', body, re.S)]
        m = re.search(id_pattern, body)
        msrc = re.search(r'src="(https://patchwiki[^"]+)"', body)
        if m and len(cells) >= 13:
            out[int(m.group(1))] = (cells, msrc.group(1) if msrc else None)
    return out


def parse_time(s):
    """'第三年2月后' / '第二年12月前、第三年12月前' → [(year, month, half), ...]"""
    res = []
    for m in re.finditer(r'第([一二三])年\s*(\d{1,2})月\s*(前|后)', s or ''):
        res.append({'year': '一二三'.index(m.group(1)) + 1,
                    'month': int(m.group(2)), 'half': m.group(3)})
    return res


def norm_grade(s):
    s = (s or '').replace('Ⅰ', '1').replace('Ⅱ', '2').replace('Ⅲ', '3')
    s = s.replace('Ⅰ', '1').replace(' ', '')
    return s


def hi_res(url):
    """BWIKI 缩略图 URL 升档到 300px（原图 512x256）。"""
    if not url:
        return url
    return re.sub(r'/\d+px-', '/300px-', url)


IMG_DIR = 'resource/umamusume/data/race_imgs'


def download_imgs(races, workers=8):
    """并发下载比赛图标到 IMG_DIR/<id>.png（已存在则跳过）。"""
    from concurrent.futures import ThreadPoolExecutor

    os.makedirs(IMG_DIR, exist_ok=True)
    todo = [r for r in races if r.get('img_url')
            and not os.path.isfile(os.path.join(IMG_DIR, '%d.png' % r['id']))]
    ok = fail = 0

    def _one(r):
        p = os.path.join(IMG_DIR, '%d.png' % r['id'])
        for _ in range(2):
            try:
                req = urllib.request.Request(r['img_url'], headers=HEADERS)
                data = urllib.request.urlopen(req, timeout=30).read()
                if len(data) > 500:
                    open(p, 'wb').write(data)
                    return True
            except Exception:
                pass
        return False

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for good in ex.map(_one, todo):
            ok += good
            fail += not good
    print(f'imgs: {len(todo)} to download, ok={ok}, fail={fail}, '
          f'total={len(os.listdir(IMG_DIR))}')
    return fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fetch', action='store_true', help='忽略缓存重新抓取')
    args = ap.parse_args()
    if args.fetch:
        for f in ('race_jp.html', 'race_cn.html'):
            p = os.path.join(CACHE, f)
            if os.path.isfile(p):
                os.remove(p)

    jp_html = fetch_page('比赛', 'race_jp.html')
    cn_html = fetch_page('简中比赛', 'race_cn.html')
    jp = parse_table(jp_html, r'alt="Thum race rt 000 (\d{4})')
    cn = parse_table(cn_html, r'alt="Jian thum race rt 000 (\d{4})')
    print(f'jp races: {len(jp)}, cn races: {len(cn)}')
    assert cn.keys() <= jp.keys(), '简中 id 超出日服 id 集合，页面结构可能已变'

    races = []
    for rid in sorted(jp):
        j, jimg = jp[rid]
        c = cn.get(rid)
        cimg = c[1] if c else None
        c = c[0] if c else None
        # jp: 0图标 1名称(日) 2中文名 3繁译名 4时间 5等级 6地点 7场地 8长度
        #     9赛程 10方向 11奖励粉丝 12所需粉丝 13成绩点 14商店币 15备注 16属性
        # cn: 0图标 1名称(简中权威) 2时间 10奖励粉丝 11所需粉丝 12备注 13属性
        name = c[1] if c else j[2]           # 简中服权威名，日服独有则用 wiki 中文名
        note = (c[12] if c and c[12] else
                NOTE_MAP.get(j[15], j[15]) if j[15] else '')
        attrs = [a.strip() for a in (c[13] if c else j[16]).replace('，', ',').split(',')
                 if a.strip()]
        races.append({
            'id': rid,
            'name': name,
            'name_source': 'cn' if c else 'jp',
            'jp_name': j[1],
            'wiki_cn_name': j[2],
            'tw_name': j[3],
            'img_url': hi_res(cimg or jimg),
            'times': parse_time(c[2] if c else j[4]),
            'time_text': c[2] if c else j[4],
            'grade': norm_grade(j[5]),
            'venue': VENUE_MAP.get(j[6], j[6]),
            'venue_jp': j[6],
            'track': TRACK_MAP.get(j[7], j[7]),
            'distance': int(j[8]) if j[8].isdigit() else j[8],
            'course': j[9],
            'direction': j[10],
            'lane': (c[9] if c and len(c) > 9 and c[9] else ''),
            'fan_reward': int(j[11]) if j[11].isdigit() else None,
            'fan_need': int(j[12]) if j[12].isdigit() else None,
            'grade_pt': int(j[13]) if len(j) > 13 and j[13].isdigit() else None,
            'shop_pt': int(j[14]) if len(j) > 14 and j[14].isdigit() else None,
            'note': note,
            'attrs': attrs,
        })

    # race.csv → bwiki id 映射（供模板 id 反查权威译名）
    jp_by_cn = {j[2]: rid for rid, (j, _) in jp.items()}
    jp_by_jp = {j[1]: rid for rid, (j, _) in jp.items()}
    cn_by_name = {c[1]: rid for rid, (c, _) in cn.items()}

    def _typo_fix(name):
        # race.csv 存在 スタークス 错字（应为 ステークス）
        return name.replace('スタークス', 'ステークス')

    csv_map = {}
    if os.path.isfile(RACE_CSV):
        with open(RACE_CSV, encoding='utf-8-sig') as f:
            for row in csv.reader(f):
                if len(row) < 4:
                    continue
                name = row[3].strip()
                rid = (cn_by_name.get(name) or jp_by_cn.get(name)
                       or jp_by_jp.get(name) or jp_by_jp.get(_typo_fix(name))
                       or jp_by_cn.get(_typo_fix(name)))
                if rid is not None:
                    csv_map[row[1]] = rid
    by_id = {r['id']: r for r in races}
    for csv_id, rid in csv_map.items():
        by_id[rid].setdefault('csv_ids', []).append(csv_id)

    n_mapped = sum(1 for r in races if r.get('csv_ids'))
    n_cn = sum(1 for r in races if r['name_source'] == 'cn')

    # 下载比赛图标（已存在跳过），把本地相对路径写进记录
    download_imgs(races)
    for r in races:
        p = os.path.join(IMG_DIR, '%d.png' % r['id'])
        if os.path.isfile(p):
            r['img'] = IMG_DIR + '/%d.png' % r['id']

    out = {
        'meta': {
            'source': ['BWIKI:比赛', 'BWIKI:简中比赛'],
            'desc': '简中服权威译名以 name_source=cn 为准；grade/场地/赛程等数值与日服一致（已验证零差异）',
            'race_count': len(races),
            'cn_named': n_cn,
            'csv_mapped': n_mapped,
        },
        'races': races,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f'written {OUT}: {len(races)} races ({n_cn} cn-named, {n_mapped} csv-mapped)')

    # 译名差异报告（简中服改名 vs wiki 日服表中文名）
    diffs = [(r['id'], r['wiki_cn_name'], r['name'])
             for r in races if r['name_source'] == 'cn' and r['name'] != r['wiki_cn_name']]
    print(f'\n简中服改名比赛: {len(diffs)} 场')
    for rid, old, new in diffs[:40]:
        print(f'  {rid}: {old} -> {new}')


if __name__ == '__main__':
    main()
