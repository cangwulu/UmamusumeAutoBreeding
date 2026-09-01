# -*- coding: utf-8 -*-
"""生成 docs/race_gallery.html —— 全量比赛浏览页（图片 + 筛选 + 搜索）。

从 race_bwiki.json 生成静态 HTML（相对路径引用 race_imgs/），
在浏览器打开即可按 等级/场地/赛程 筛选、按名字搜索。
"""
import json
import os

DATA = 'resource/umamusume/data/race_bwiki.json'
OUT = 'docs/race_gallery.html'

GRADE_ORDER = {'G1': 0, 'G2': 1, 'G3': 2, 'OP': 3, 'Pre-OP': 4, '': 5}


def time_key(r):
    if not r['times']:
        return (9, 9, True)
    t = r['times'][0]
    return (t['year'], t['month'], t['half'] != '前')


def main():
    with open(DATA, encoding='utf-8') as f:
        races = json.load(f)['races']
    races.sort(key=lambda r: (GRADE_ORDER.get(r['grade'], 9), time_key(r), r['id']))

    cards = []
    for r in races:
        img = r.get('img', '')
        img_rel = '../' + img if img else ''
        time_txt = r['time_text'] or '时间未知'
        fan = ''
        if r['fan_reward'] is not None:
            fan = f"粉丝 +{r['fan_reward']} / 需 {r['fan_need']}"
        jp = r['jp_name'] if r['name_source'] == 'cn' else ''
        alias = r['wiki_cn_name'] if (r['name_source'] == 'cn'
                                      and r['wiki_cn_name'] != r['name']) else ''
        note = r['note'] or ''
        attrs = '、'.join(r['attrs']) if r['attrs'] else ''
        meta = f"{r['venue']} · {r['track']} {r['distance']}m · {r['course']}"
        if r['direction']:
            meta += f" · {r['direction']}"
        detail = ' · '.join(x for x in (time_txt, fan, attrs) if x)
        cards.append(f'''<div class="card" data-grade="{r['grade']}" data-venue="{r['venue']}"
     data-course="{r['course']}" data-name="{r['name']}" data-alias="{alias}"
     data-jp="{jp}">
  <div class="banner">{'<img loading="lazy" src="%s" alt="%s">' % (img_rel, r['name']) if img_rel else '<span class="noimg">无图</span>'}</div>
  <div class="info">
    <div class="title"><span class="g g-{r['grade'].replace('-', '')}">{r['grade']}</span> {r['name']}</div>
    <div class="sub">{alias}{(' / ' + jp) if jp else ''}</div>
    <div class="meta">{meta}</div>
    <div class="detail">{detail}</div>
    {f'<div class="note">{note}</div>' if note else ''}
  </div>
</div>''')

    grades = ['G1', 'G2', 'G3', 'OP', 'Pre-OP']
    venues = sorted({r['venue'] for r in races if r['venue']})
    courses = ['短距离', '英里赛', '中距离', '长距离']

    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>赛马娘简中服 比赛图鉴（313 场）</title>
<style>
body {{ font-family: "Microsoft YaHei", "Segoe UI", sans-serif; margin: 0;
  background: #f5f6fa; color: #2c2c34; }}
header {{ position: sticky; top: 0; z-index: 10; background: #fff;
  padding: 10px 18px; box-shadow: 0 1px 6px rgba(0,0,0,.08); }}
h1 {{ font-size: 17px; margin: 4px 0 8px; }}
.filters {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.chip {{ border: 1px solid #d0d3e0; border-radius: 14px; padding: 3px 12px;
  font-size: 13px; cursor: pointer; background: #fff; user-select: none; }}
.chip.on {{ background: #4a6cf7; color: #fff; border-color: #4a6cf7; }}
#q {{ border: 1px solid #d0d3e0; border-radius: 14px; padding: 4px 12px;
  font-size: 13px; width: 200px; outline: none; }}
#count {{ font-size: 12px; color: #8a8f9e; margin-left: 8px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px; padding: 16px 18px; }}
.card {{ background: #fff; border-radius: 10px; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,.07); transition: transform .12s; }}
.card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,.12); }}
.banner img {{ width: 100%; display: block; background: #eee; }}
.banner .noimg {{ display: block; height: 60px; line-height: 60px; text-align: center;
  color: #aaa; background: #eee; }}
.info {{ padding: 8px 12px 10px; }}
.title {{ font-size: 15px; font-weight: 700; }}
.g {{ display: inline-block; border-radius: 4px; font-size: 11px; padding: 1px 5px;
  margin-right: 4px; vertical-align: 1px; color: #fff; }}
.g-G1 {{ background: #e8a000; }} .g-G2 {{ background: #d05a5a; }}
.g-G3 {{ background: #4a7fd0; }} .g-OP {{ background: #4caf7d; }}
.g-PreOP {{ background: #8a8f9e; }}
.sub {{ font-size: 11px; color: #9aa0ae; margin-top: 2px; min-height: 14px; }}
.meta {{ font-size: 12.5px; color: #4c5566; margin-top: 4px; }}
.detail {{ font-size: 12px; color: #8a8f9e; margin-top: 2px; }}
.note {{ font-size: 11.5px; color: #b07c2a; margin-top: 3px; }}
</style></head><body>
<header>
  <h1>赛马娘简中服 · 比赛图鉴 <small style="font-weight:400;color:#8a8f9e">（译名以 BWIKI「简中比赛」为准 · 数据源 race_bwiki.json）</small></h1>
  <div class="filters">
    <input id="q" placeholder="搜索比赛名 / 旧译名 / 日文名">
    <span id="grade-filters">{''.join(f'<span class="chip" data-f="grade" data-v="{g}">{g}</span>' for g in grades)}</span>
    <span id="course-filters">{''.join(f'<span class="chip" data-f="course" data-v="{c}">{c}</span>' for c in courses)}</span>
    <span id="count"></span>
  </div>
  <div class="filters" style="margin-top:6px">
    <span id="venue-filters">{''.join(f'<span class="chip" data-f="venue" data-v="{v}">{v}</span>' for v in venues)}</span>
  </div>
</header>
<div class="grid" id="grid">{''.join(cards)}</div>
<script>
const sel = {{grade: new Set(), venue: new Set(), course: new Set()}};
document.querySelectorAll('.chip').forEach(c => {{
  c.onclick = () => {{
    const s = sel[c.dataset.f];
    if (s.has(c.dataset.v)) {{ s.delete(c.dataset.v); c.classList.remove('on'); }}
    else {{ s.add(c.dataset.v); c.classList.add('on'); }}
    apply();
  }};
}});
document.getElementById('q').oninput = apply;
function apply() {{
  const q = document.getElementById('q').value.trim();
  let n = 0;
  document.querySelectorAll('.card').forEach(el => {{
    let ok = true;
    if (sel.grade.size && !sel.grade.has(el.dataset.grade)) ok = false;
    if (ok && sel.venue.size && !sel.venue.has(el.dataset.venue)) ok = false;
    if (ok && sel.course.size && !sel.course.has(el.dataset.course)) ok = false;
    if (ok && q) {{
      const hay = el.dataset.name + '|' + el.dataset.alias + '|' + el.dataset.jp;
      ok = hay.includes(q);
    }}
    el.style.display = ok ? '' : 'none';
    if (ok) n++;
  }});
  document.getElementById('count').textContent = n + ' / {len(races)} 场';
}}
apply();
</script>
</body></html>'''

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    print('written', OUT, len(races), 'races')


if __name__ == '__main__':
    main()
