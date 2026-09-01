"""chara_targets.py — 角色育成目标比赛查询模块。

数据源: resource/umamusume/data/chara_targets.json (81 角色 / 744 目标)
        resource/umamusume/data/race_bwiki.json (比赛译名归一)

核心接口:
    load_targets(name)         -> 角色目标列表 (含时间/粉丝门槛/比赛描述)
    targets_with_race(name)    -> 目标 + 关联的 race_bwiki Race 对象 (译名归一后)
    next_target(name, y, m, h) -> 当前时间之后的下一个目标
    fan_milestones(name)       -> 粉丝门槛时间线 [(time, fan_need)]

CLI:
    python module/umamusume/asset/chara_targets.py 特别周
    python module/umamusume/asset/chara_targets.py 特别周 --resolve   # 含译名归一
    python module/umamusume/asset/chara_targets.py 特别周 --next 2 6 前
"""
import os, sys, json

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_DATA_DIR = os.path.join(_PROJECT_ROOT, 'resource', 'umamusume', 'data')
_TARGETS_JSON = os.path.join(_DATA_DIR, 'chara_targets.json')


def _load_raw():
    return json.load(open(_TARGETS_JSON, encoding='utf-8'))


def _normalize_name(name: str) -> str:
    """处理 BWIKI 子页名与 character_bwiki name 的译名差异."""
    FIX = {
        '东海帝皇': '东海帝王', '富士奇迹': '富士奇石', '春乌拉拉': '春乌菈菈',
        '第一红宝石': '第一红宝', '艾尼斯风神': '艾尼风神', '菱钻奇宝': '菱奇宝',
        '葛城王牌': '葛城荣主', '超级小海湾': '超级溪流', '目白赖恩': '目白莱恩',
        '目白阿尔丹': '目白雅丹', '东瀛佐敦': '岛川乔丹', '真弓快车': '阿斯顿真弓',
        '天狼星象征': '克里斯象征', '摩耶重炮': '重炮',
    }
    return FIX.get(name, name)


def resolve_character(query: str):
    """模糊匹配角色名 (支持 card_name 和 name). 返回 character dict 或 None."""
    d = _load_raw()
    q = query.strip()
    # 完全匹配
    for c in d['characters']:
        if c['name'] == q or q in c['card_names']:
            return c
    # 模糊: name 包含
    for c in d['characters']:
        if q in c['name'] or any(q in cn for cn in c['card_names']):
            return c
    # 反向: name 包含 query
    for c in d['characters']:
        if c['name'] in q:
            return c
    return None


def load_targets(name: str):
    """返回角色的目标列表. 多形态歧义时报错."""
    c = resolve_character(name)
    if c is None:
        return None
    return c['targets']


def _try_resolve_race(race_desc: str, title: str = ''):
    """尝试用 race_bwiki 把比赛描述里的日文名映射到简中权威名."""
    try:
        sys.path.insert(0, os.path.join(_PROJECT_ROOT, 'module', 'umamusume', 'asset'))
        from race_bwiki import resolve as _resolve
        # title 通常是日文比赛名 (如 きさらぎ賞で5着以内), 提取比赛名部分
        import re
        m = re.match(r'(.+?)(?:で|に|を|の)', title)
        cand = m.group(1) if m else title.split()[0] if title else ''
        if cand:
            r = _resolve(cand)
            if r:
                return r
        # race_desc 第一段可能是等级+场地, 尝试用 venue+距离 反查
    except Exception:
        pass
    return None


def targets_with_race(name: str):
    """目标列表 + 关联的 race_bwiki Race 对象 (译名归一)."""
    targets = load_targets(name)
    if targets is None:
        return None
    out = []
    for t in targets:
        race = _try_resolve_race(t.get('race_desc', ''), t.get('title', ''))
        out.append({**t, 'resolved_race': race})
    return out


def next_target(name: str, year: int, month: int, half: str):
    """当前时间 (year/month/half) 之后的下一个目标. half='前'/'后'."""
    targets = load_targets(name)
    if targets is None:
        return None
    half_order = {'前': 0, '后': 1}
    cur_key = (year, month, half_order.get(half, 0))
    for t in targets:
        tm = t.get('time')
        if not tm:
            continue
        key = (tm['year'], tm['month'], half_order.get(tm['half'], 0))
        if key >= cur_key:
            return t
    return None


def fan_milestones(name: str):
    """粉丝门槛时间线 [(time_text, fan_need, target_title)]."""
    targets = load_targets(name)
    if targets is None:
        return None
    out = []
    for t in targets:
        if t.get('fan_need'):
            out.append({
                'time_text': t.get('time_text', ''),
                'time': t.get('time'),
                'fan_need': t['fan_need'],
                'title': t.get('title', ''),
            })
    out.sort(key=lambda x: ((x['time'] or {}).get('year', 0),
                            (x['time'] or {}).get('month', 0),
                            x['time'] or {'half': '前'}['half']))
    return out


def main():
    args = sys.argv[1:]
    if not args:
        d = _load_raw()
        print(f"chara_targets: {d['meta']['chara_count']} chars, {d['meta']['target_count']} targets")
        print(f"usage: {sys.argv[0]} <角色名> [--resolve] [--next Y M 半]")
        return 0
    name = args[0]
    do_resolve = '--resolve' in args
    if '--next' in args:
        i = args.index('--next')
        y, m, h = int(args[i + 1]), int(args[i + 2]), args[i + 3]
        t = next_target(name, y, m, h)
        if t:
            print(f"下一个目标: #{t['index']} {t['title']}")
            print(f"  时间: {t['time_text']}  粉丝门槛: {t.get('fan_need') or '无'}")
            print(f"  比赛: {t['race_desc'][:70]}")
        else:
            print('无后续目标')
        return 0
    if do_resolve:
        ts = targets_with_race(name)
    else:
        ts = load_targets(name)
    if ts is None:
        print(f'未找到角色: {name}')
        return 1
    print(f'{name} 育成目标 ({len(ts)} 个):')
    for t in ts:
        fn = f" 粉丝≥{t['fan_need']}" if t.get('fan_need') else ''
        rr = ''
        if do_resolve and t.get('resolved_race'):
            rr = f"  → {t['resolved_race'].name} ({t['resolved_race'].grade})"
        print(f"  #{t['index']} {t['title']}")
        print(f"     {t['time_text']}{fn}  {t.get('race_desc','')[:60]}{rr}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
