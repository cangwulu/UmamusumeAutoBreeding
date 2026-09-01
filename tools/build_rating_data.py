# -*- coding: utf-8 -*-
"""构建技能升级链数据 skill_upgrade.json（含评分计算器的技能表）

数据来源：BWIKI「简中评分计算器」页面
  https://wiki.biligame.com/umamusume/简中评分计算器
页面用 561 个微型 <script> 逐条 push 技能对象（var skraw={...}; skillData.push(skraw)），
每条含 group_id（技能家族）与 类型（升级链位置）。

产出：resource/umamusume/data/skill_upgrade.json
  - groups: 技能家族列表，每个家族含成员（基础/升级/上位/负面）
  - 类型含义：1=基础(○) / 2=升级(◎) / 3=上位(金技) / -1=负面(×，紫色)
  - 这是 skill_bwiki.json（纯评分）没有的**升级链结构**：
    同 group 内 学习上位版本可替代/覆盖下位版本（评分计算器里勾选上位会禁用下位）

用法：
  python tools/build_rating_data.py            # 用 tools/.cache/score_calc.html
  python tools/build_rating_data.py --fetch    # 先重新抓取页面
"""
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
CACHE = os.path.join(ROOT, 'tools', '.cache')
SRC = os.path.join(CACHE, 'score_calc.html')
OUT = os.path.join(ROOT, 'resource', 'umamusume', 'data', 'skill_upgrade.json')

SOURCE_PAGE = '简中评分计算器'
SOURCE_URL = 'https://wiki.biligame.com/umamusume/' + SOURCE_PAGE

TYPE_NAMES = {1: '基础', 2: '升级', 3: '上位', -1: '负面'}
# 评分计算器里硬编码 特殊=1 的技能（固有类，不吃适性倍率）
SPECIAL_IDS = {201671, 201672}


def fetch():
    import urllib.request
    import urllib.parse

    wiki = 'https://wiki.biligame.com/umamusume'
    url = wiki + '/api.php?' + urllib.parse.urlencode(
        {'action': 'parse', 'page': SOURCE_PAGE, 'prop': 'text', 'format': 'json'})
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
        'Referer': wiki + '/' + urllib.parse.quote(SOURCE_PAGE),
        'Accept': 'application/json',
    })
    html = json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))
    text = html['parse']['text']['*']
    os.makedirs(CACHE, exist_ok=True)
    open(SRC, 'w', encoding='utf-8').write(text)
    print('cached %s (%d bytes)' % (SRC, len(text)))


def extract_skills(html):
    rows = []
    for m in re.finditer(r'var skraw=\{(.*?)\};\s*skillData\.push', html, re.S):
        d = {}
        for km in re.finditer(r'"(\w+)":(?:parseInt\("([^"]*)"\)|"([^"]*)"|(-?\d+))', m.group(1)):
            k, pint, pstr, pnum = km.groups()
            d[k] = int(pint or pnum) if (pint or pnum) else pstr
        if 'id' in d:
            rows.append(d)
    return rows


def build():
    html = open(SRC, encoding='utf-8').read()
    rows = extract_skills(html)
    print('skills extracted:', len(rows))

    groups = {}
    for r in rows:
        sid = r['id']
        g = groups.setdefault(r['group_id'], [])
        g.append({
            'id': sid,
            'name': r.get('中文名', ''),
            'jp': r.get('技能名', ''),
            'condition': r.get('条件限制', ''),
            'score': int(r.get('评价分', 0)),
            'pt': int(r.get('所需技能PT', 0)),
            'type': r.get('类型', 1),
            'type_name': TYPE_NAMES.get(r.get('类型', 1), str(r.get('类型'))),
            'color': r.get('颜色', ''),
            'special': 1 if sid in SPECIAL_IDS else r.get('特殊', 0),
        })

    # 组内排序：负面 < 基础 < 升级 < 上位
    order = {-1: 0, 1: 1, 2: 2, 3: 3}
    group_list = []
    for gid in sorted(groups):
        members = sorted(groups[gid], key=lambda x: order.get(x['type'], 9))
        group_list.append({
            'group_id': gid,
            'members': members,
        })

    multi = sum(1 for g in group_list if len(g['members']) > 1)
    out = {
        'meta': {
            'source': 'BWIKI 简中评分计算器',
            'url': SOURCE_URL,
            'built': str(date.today()),
            'skill_count': len(rows),
            'group_count': len(group_list),
            'multi_member_groups': multi,
            'type_semantics': {
                '1': '基础(○)', '2': '升级(◎)', '3': '上位(金技)', '-1': '负面(×，紫色)',
            },
            'note': '评分计算器中勾选升级/上位版本会自动禁用同组下位版本；'
                    'special=1 的技能不吃适性倍率（评价分×1）',
        },
        'groups': group_list,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('written %s (%d skills, %d groups, %d multi) %.0f KB'
          % (OUT, len(rows), len(group_list), multi, os.path.getsize(OUT) / 1024))


if __name__ == '__main__':
    if '--fetch' in sys.argv or not os.path.exists(SRC):
        fetch()
    build()
