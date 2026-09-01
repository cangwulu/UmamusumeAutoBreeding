# -*- coding: utf-8 -*-
"""构建相性数据资产 affinity.json

数据来源：BWIKI「简中相性计算器」页面
  https://wiki.biligame.com/umamusume/简中相性计算器
页面内嵌两个隐藏 JSON 容器（#relation / #chara），由本仓库的抓取步骤缓存到：
  tools/.cache/affinity_relation.json   关系组列表（1274 组，简中服实装角色）
  tools/.cache/affinity_chara.json      角色列表（76 个，id → 中文名）

产出：resource/umamusume/data/affinity.json
  - characters: id -> 中文名（清洗零宽字符后）
  - groups:     关系组（type/point/category/detail/member_ids）
  - meta:       来源 / 数据版本 / 计算方法说明

用法（先跑抓取，再跑构建）：
  python tools/fetch_affinity.py   # 或手工执行本文件内的 fetch()
  python tools/build_affinity.py
"""
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
CACHE = os.path.join(ROOT, 'tools', '.cache')
OUT = os.path.join(ROOT, 'resource', 'umamusume', 'data', 'affinity.json')

SOURCE_PAGE = '简中相性计算器'
SOURCE_URL = 'https://wiki.biligame.com/umamusume/' + SOURCE_PAGE

# 零宽 / 方向控制字符（wiki 数据里混入了 \u200e 等不可见字符）
_INVISIBLE = re.compile(r'[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2060\ufeff]')


def _clean(s):
    return _INVISIBLE.sub('', s).strip() if isinstance(s, str) else s


def fetch():
    """从 BWIKI 抓取计算器页面并提取 #relation / #chara 两个隐藏 JSON。"""
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
    open(os.path.join(CACHE, 'affinity_calc.html'), 'w', encoding='utf-8').write(text)

    def grab(pid):
        m = re.search(r'<[^>]*id="%s"[^>]*>' % pid, text)
        if not m:
            raise RuntimeError('container #%s not found' % pid)
        tag = m.group(0)
        close = '</' + re.match(r'<(\w+)', tag).group(1) + '>'
        return text[m.end():text.find(close, m.end())]

    os.makedirs(CACHE, exist_ok=True)
    for pid, fname in [('relation', 'affinity_relation.json'), ('chara', 'affinity_chara.json')]:
        data = json.loads(grab(pid))
        with open(os.path.join(CACHE, fname), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print('cached %s: %d entries' % (fname, len(data)))

    # 数据版本（页面正文里的「数据版本: YYYY/MM/DD」）
    m = re.search(r'数据版本[:：]\s*([\d/]+)', text)
    version = m.group(1) if m else ''
    with open(os.path.join(CACHE, 'affinity_version.txt'), 'w', encoding='utf-8') as f:
        f.write(version)
    print('data version:', version or '(not found)')


def build():
    relation = json.load(open(os.path.join(CACHE, 'affinity_relation.json'), encoding='utf-8'))
    chara = json.load(open(os.path.join(CACHE, 'affinity_chara.json'), encoding='utf-8'))
    version = ''
    vpath = os.path.join(CACHE, 'affinity_version.txt')
    if os.path.exists(vpath):
        version = open(vpath, encoding='utf-8').read().strip()

    characters = {}
    for c in chara:
        cid = c.get('id')
        name = _clean(c.get('中文名', ''))
        if not cid or not name or cid == 0:
            continue
        characters[cid] = name

    groups = []
    for g in relation:
        member_ids = sorted(set(g.get('member_id', [])))
        if len(member_ids) < 2:
            continue  # 单人组（如独居宿舍）不产生任何配对/三人组分数
        groups.append({
            'type': g.get('relation_type'),
            'point': g.get('relation_point', 0),
            'category': _clean(g.get('分类', '')),
            'detail': _clean(g.get('补充', '')),
            'members': member_ids,
        })

    # 角色表可能有缺漏（实测缺 9 个实装角色），从关系组的「成员」字段按位置对齐补齐
    for g in relation:
        ids = g.get('member_id', [])
        names = [x for x in (_clean(n) for n in _clean(g.get('成员', '')).split(',')) if x]
        if len(ids) != len(names):
            continue  # 对不齐就放弃这一组，宁缺毋滥
        for cid, name in zip(ids, names):
            if cid and name and cid not in characters:
                characters[cid] = name
                print('recovered missing chara: %s -> %s' % (cid, name))

    # 校验：member_id 是否都能在角色表里找到
    known = set(characters)
    unknown = {i for g in groups for i in g['members'] if i not in known}
    if unknown:
        print('WARN: %d member ids missing from chara list: %s' % (len(unknown), sorted(unknown)))

    out = {
        'meta': {
            'source': 'BWIKI 简中相性计算器',
            'url': SOURCE_URL,
            'data_version': version,
            'built': str(date.today()),
            'character_count': len(characters),
            'group_count': len(groups),
            'method': {
                'pair_score': '两角色固定相性分 = 两者共同所在关系组的 point 之和',
                'triple_score': '三角色固定相性分 = 三者共同所在关系组的 point 之和',
                'inherit_tree': '目标马(0)/父母1(1)/父母2(2)/祖父母1~4(3~6)；'
                                '1号=组(0,1)；2号=组(0,2)+组(1,2)；'
                                '3号=组(0,1,3)；4号=组(0,1,4)；5号=组(0,2,5)；6号=组(0,2,6)；'
                                '祖父母与目标马同角色时该号记 0 分',
                'grade': '△ ≥0 / 〇 ≥51 / ⌾ ≥151',
                'win_saddle_note': '本数据不含胜鞍加成：同一分支上每有一场相同比赛的'
                                   '夺冠履历（G1 胜鞍重合，OP/Pre-OP/新马战/URA 不计）额外 +1pt，'
                                   '需另行计算',
            },
        },
        'characters': characters,
        'groups': groups,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    size_kb = os.path.getsize(OUT) / 1024
    print('written %s (%d chars, %d groups, %.0f KB)' % (OUT, len(characters), len(groups), size_kb))


if __name__ == '__main__':
    if '--fetch' in sys.argv or not os.path.exists(os.path.join(CACHE, 'affinity_relation.json')):
        fetch()
    build()
