# -*- coding: utf-8 -*-
"""urarawin 数据库集成：交叉比对 + 提取互补数据。

数据源：UmaUmaCruise-db-urarawin-master/UmaMusumeLibrary.json（简中版，4MB）
       UmaMusumeLibrary.jp.json（日文版，4MB）

urarawin 数据结构：
    {
      "Charactor": {"☆3": {"[卡名]角色名": {"Event": [{事件名: [{Option, Effect}, ...]}, ...]}}, ...},
      "Support":   {"SSR": {"［卡名］角色名": {"Event": [...]}, ...}, "SR": {...}, "R": {...}},
      "Skill":     {"ノーマル": [{Name, Effect}, ...], "レア": [...], "固有": [...], "Buff": [...]},
      "Race":      {"G1": [{Name, Location, GroundCondition, DistanceClass, Distance, Rotation, Date}, ...], ...}
    }

互补价值：
    1. 支援卡事件 757 条 — 我们完全没有
    2. 角色事件 5108 条 vs 我们 2213 条 — urarawin 更多
    3. 技能效果中文 559 个 — 可补 skill_bwiki.json 的效果文本
    4. 比赛 279 场 — 子集，用于验证 race_bwiki.json

用法：
    python tools/integrate_urarawin.py              # 交叉比对 + 输出报告
    python tools/integrate_urarawin.py --build      # 生成 JSON 数据文件
"""

import json
import os
import sys
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'resource', 'umamusume', 'data')

# urarawin 数据路径（在工作区上级目录）
URARAWIN_DIR = os.path.join(os.path.dirname(PROJECT_ROOT),
                            'UmaUmaCruise-db-urarawin-master',
                            'UmaUmaCruise-db-urarawin-master')
URARAWIN_CN = os.path.join(URARAWIN_DIR, 'UmaMusumeLibrary.json')
URARAWIN_JP = os.path.join(URARAWIN_DIR, 'UmaMusumeLibrary.jp.json')

# 我们的数据路径
BWIKI_RACE = os.path.join(DATA_DIR, 'race_bwiki.json')
CHARA_EVENTS = os.path.join(DATA_DIR, 'chara_events.json')
SKILL_BWIKI = os.path.join(DATA_DIR, 'skill_bwiki.json')

# 输出路径
OUT_SUPPORT_EVENTS = os.path.join(DATA_DIR, 'support_events.json')
OUT_CROSSREF = os.path.join(DATA_DIR, 'urarawin_crossref.json')


def load_urarawin():
    with open(URARAWIN_CN, encoding='utf-8') as f:
        return json.load(f)


def extract_support_events(data):
    """提取支援卡事件 → 结构化列表。

    输出格式：
    [
      {
        "card_name": "［輝く景色の、その先に］サイレンススズカ",
        "rarity": "SSR",
        "chara_name": "サイレンススズカ",
        "card_title": "輝く景色の、その先に",
        "events": [
          {
            "event_name": "どこまでも",
            "options": [
              {"option": "構わないよ", "effect": "スピード(速度)+10\\nスタミナ(耐力)+5\\nサイレンススズカの絆ゲージ+5"},
              {"option": "全力で走ってみて", "effect": "スピード(速度)+15\\nサイレンススズカの絆ゲージ+5"}
            ]
          }
        ]
      }
    ]
    """
    results = []
    for rarity in ('SSR', 'SR', 'R'):
        cards = data['Support'].get(rarity, {})
        for card_name, card_data in cards.items():
            # 解析卡名：［标题］角色名 或 [标题]角色名
            chara_name = card_name
            card_title = ''
            # 全角括号 ［...］
            if card_name.startswith('［') and '］' in card_name:
                idx = card_name.index('］')
                card_title = card_name[1:idx]
                chara_name = card_name[idx+1:]
            # 半角括号 [...]
            elif card_name.startswith('[') and ']' in card_name:
                idx = card_name.index(']')
                card_title = card_name[1:idx]
                chara_name = card_name[idx+1:]

            events = []
            for ev in card_data.get('Event', []):
                for ev_name, options in ev.items():
                    opts = []
                    for opt in options:
                        opts.append({
                            'option': opt.get('Option', ''),
                            'effect': opt.get('Effect', ''),
                        })
                    events.append({
                        'event_name': ev_name,
                        'options': opts,
                    })

            results.append({
                'card_name': card_name,
                'rarity': rarity,
                'chara_name': chara_name,
                'card_title': card_title,
                'event_count': len(events),
                'events': events,
            })
    return results


def extract_chara_events(data):
    """提取角色事件（urarawin 格式）→ 统计 + 结构化。"""
    results = []
    for star, chars in data['Charactor'].items():
        for char_name, char_data in chars.items():
            # 解析角色名
            name = char_name
            card_title = ''
            if char_name.startswith('[') and ']' in char_name:
                idx = char_name.index(']')
                card_title = char_name[1:idx]
                name = char_name[idx+1:]
            elif char_name.startswith('［') and '］' in char_name:
                idx = char_name.index('］')
                card_title = char_name[1:idx]
                name = char_name[idx+1:]

            events = []
            for ev in char_data.get('Event', []):
                for ev_name, options in ev.items():
                    opts = []
                    for opt in options:
                        opts.append({
                            'option': opt.get('Option', ''),
                            'effect': opt.get('Effect', ''),
                        })
                    events.append({
                        'event_name': ev_name,
                        'options': opts,
                    })

            results.append({
                'chara_key': char_name,
                'chara_name': name,
                'card_title': card_title,
                'star': star,
                'event_count': len(events),
                'events': events,
            })
    return results


def crossref_races(urarawin_data, bwiki_data):
    """比赛交叉比对。"""
    bwiki_by_jp = {}
    for r in bwiki_data['races']:
        jp = r.get('jp_name', '')
        if jp:
            bwiki_by_jp[jp.replace(' ', '').replace('　', '')] = r

    matched = 0
    urarawin_only = []
    bwiki_only_ids = set(r['id'] for r in bwiki_data['races'])

    for grade, races in urarawin_data['Race'].items():
        for r in races:
            name_ns = r['Name'].replace(' ', '').replace('　', '')
            br = bwiki_by_jp.get(name_ns)
            if br:
                matched += 1
                bwiki_only_ids.discard(br['id'])
            else:
                urarawin_only.append(r)

    return {
        'urarawin_total': sum(len(v) for v in urarawin_data['Race'].values()),
        'matched': matched,
        'urarawin_only': len(urarawin_only),
        'bwiki_only': len(bwiki_only_ids),
        'urarawin_only_names': [r['Name'] for r in urarawin_only[:20]],
    }


def crossref_chara_events(urarawin_charas, our_events_path):
    """角色事件交叉比对。"""
    with open(our_events_path, encoding='utf-8') as f:
        our_data = json.load(f)

    # 我们的：按角色名建索引
    our_by_name = {}
    for chara in our_data.get('characters', []):
        for name in [chara.get('name', ''), chara.get('jp_name', '')]:
            if name:
                our_by_name[name] = chara

    # urarawin 的角色名（去掉卡名前缀后的纯角色名）
    urarawin_names = set()
    for c in urarawin_charas:
        urarawin_names.add(c['chara_name'])

    our_names = set(our_by_name.keys())

    # 在 urarawin 有但我们没有的角色
    urarawin_only = urarawin_names - our_names
    # 我们有但 urarawin 没有的
    our_only = our_names - urarawin_names

    return {
        'urarawin_chars': len(urarawin_names),
        'our_chars': len(our_names),
        'common': len(urarawin_names & our_names),
        'urarawin_only': sorted(urarawin_only),
        'our_only': sorted(our_only),
    }


def crossref_skills(urarawin_data, skill_bwiki_path):
    """技能交叉比对。"""
    if not os.path.exists(skill_bwiki_path):
        return {'error': 'skill_bwiki.json not found'}

    with open(skill_bwiki_path, encoding='utf-8') as f:
        our_skills = json.load(f)

    # urarawin 技能名集合
    urarawin_names = set()
    urarawin_effects = {}
    for cat, skills in urarawin_data['Skill'].items():
        for s in skills:
            urarawin_names.add(s['Name'])
            urarawin_effects[s['Name']] = s.get('Effect', '')

    # 我们的技能名集合
    our_names = set()
    for s in our_skills.get('skills', []):
        for key in ('name', 'jp_name', 'cn_name'):
            if s.get(key):
                our_names.add(s[key])

    return {
        'urarawin_skills': len(urarawin_names),
        'our_skills': len(our_names),
        'common': len(urarawin_names & our_names),
        'urarawin_only': len(urarawin_names - our_names),
        'our_only': len(our_names - urarawin_names),
    }


def main():
    do_build = '--build' in sys.argv
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    print('=' * 60)
    print('urarawin 数据库集成')
    print('=' * 60)

    # 1. 加载
    data = load_urarawin()
    print(f'\n[加载] urarawin 数据: {os.path.getsize(URARAWIN_CN)//1024}KB')

    # 统计
    for cat in ('Charactor', 'Support', 'Skill', 'Race'):
        total = sum(len(v) for v in data[cat].values())
        print(f'  {cat}: {total} ({", ".join(f"{k}:{len(v)}" for k,v in data[cat].items())})')

    # 2. 提取支援卡事件
    support_events = extract_support_events(data)
    total_sup_events = sum(c['event_count'] for c in support_events)
    print(f'\n[支援卡] {len(support_events)} 张卡, {total_sup_events} 个事件')
    rarity_counts = Counter(c['rarity'] for c in support_events)
    print(f'  稀有度: {dict(rarity_counts)}')

    if verbose:
        print('\n  支援卡事件示例:')
        for c in support_events[:3]:
            print(f'    [{c["rarity"]}] {c["card_name"]}')
            for ev in c['events'][:2]:
                print(f'      {ev["event_name"]}: {len(ev["options"])}个选项')
                for opt in ev['options'][:1]:
                    print(f'        → {opt["option"]}: {opt["effect"][:80]}')

    # 3. 提取角色事件
    chara_events = extract_chara_events(data)
    total_char_events = sum(c['event_count'] for c in chara_events)
    print(f'\n[角色] {len(chara_events)} 个角色, {total_char_events} 个事件')

    # 4. 比赛交叉比对
    print(f'\n[比赛交叉比对]')
    with open(BWIKI_RACE, encoding='utf-8') as f:
        bwiki_data = json.load(f)
    race_xref = crossref_races(data, bwiki_data)
    print(f'  urarawin: {race_xref["urarawin_total"]} 场')
    print(f'  匹配: {race_xref["matched"]}')
    print(f'  urarawin独有: {race_xref["urarawin_only"]}')
    print(f'  BWIKI独有: {race_xref["bwiki_only"]}')
    if verbose and race_xref['urarawin_only_names']:
        print(f'  urarawin独有名单: {race_xref["urarawin_only_names"][:10]}')

    # 5. 角色事件交叉比对
    print(f'\n[角色事件交叉比对]')
    chara_xref = crossref_chara_events(chara_events, CHARA_EVENTS)
    print(f'  urarawin角色: {chara_xref["urarawin_chars"]}')
    print(f'  我们角色: {chara_xref["our_chars"]}')
    print(f'  共有: {chara_xref["common"]}')
    print(f'  urarawin独有角色: {len(chara_xref["urarawin_only"])}')
    if verbose and chara_xref['urarawin_only']:
        print(f'    {chara_xref["urarawin_only"][:15]}')
    print(f'  我们独有角色: {len(chara_xref["our_only"])}')
    if verbose and chara_xref['our_only']:
        print(f'    {chara_xref["our_only"][:15]}')

    # 6. 技能交叉比对
    print(f'\n[技能交叉比对]')
    skill_xref = crossref_skills(data, SKILL_BWIKI)
    if 'error' in skill_xref:
        print(f'  {skill_xref["error"]}')
    else:
        print(f'  urarawin: {skill_xref["urarawin_skills"]} 个')
        print(f'  我们: {skill_xref["our_skills"]} 个')
        print(f'  共有: {skill_xref["common"]}')
        print(f'  urarawin独有: {skill_xref["urarawin_only"]}')
        print(f'  我们独有: {skill_xref["our_only"]}')

    # 7. 构建 JSON
    if do_build:
        print(f'\n[构建] 生成数据文件...')

        # 支援卡事件
        support_output = {
            'meta': {
                'source': 'urarawin.com (UmaMusumeLibrary.json)',
                'desc': '支援卡事件：283张卡/757个事件，含选项+效果中文',
                'total_cards': len(support_events),
                'total_events': total_sup_events,
            },
            'cards': support_events,
        }
        with open(OUT_SUPPORT_EVENTS, 'w', encoding='utf-8') as f:
            json.dump(support_output, f, ensure_ascii=False, indent=1)
        print(f'  → {OUT_SUPPORT_EVENTS} ({os.path.getsize(OUT_SUPPORT_EVENTS)//1024}KB)')

        # 交叉比对报告
        xref_output = {
            'meta': {'source': 'urarawin vs BWIKI cross-reference'},
            'race_crossref': race_xref,
            'chara_crossref': {k: v for k, v in chara_xref.items()},
            'skill_crossref': skill_xref,
        }
        with open(OUT_CROSSREF, 'w', encoding='utf-8') as f:
            json.dump(xref_output, f, ensure_ascii=False, indent=1)
        print(f'  → {OUT_CROSSREF}')

    print(f'\n[完成]')
    print(f'  核心互补: 支援卡事件 {total_sup_events} 条（全新数据）')
    print(f'  角色事件: urarawin {total_char_events} vs 我们 2213（可补充）')
    if do_build:
        print(f'  已生成: support_events.json + urarawin_crossref.json')

    return 0


if __name__ == '__main__':
    sys.exit(main())
