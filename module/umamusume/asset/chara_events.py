"""chara_events.py — 角色育成事件查询模块。

数据源: resource/umamusume/data/chara_events.json (角色专属事件含选项)

核心接口:
    load_events(name)              -> 角色事件列表
    events_with_options(name)      -> 只要有选项的事件
    find_event(name, event_name)   -> 按简中名/日文名查事件
    event_summary(name)            -> 事件统计 (总数/有选项/无选项/角色专属/通用)

CLI:
    python module/umamusume/asset/chara_events.py 特别周
    python module/umamusume/asset/chara_events.py 特别周 --detail 想和你去的地方
    python module/umamusume/asset/chara_events.py 特别周 --summary
"""
import os, sys, json

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_DATA_DIR = os.path.join(_PROJECT_ROOT, 'resource', 'umamusume', 'data')
_EVENTS_JSON = os.path.join(_DATA_DIR, 'chara_events.json')


def _load_raw():
    if not os.path.exists(_EVENTS_JSON):
        return None
    return json.load(open(_EVENTS_JSON, encoding='utf-8'))


def _normalize_name(name: str) -> str:
    FIX = {
        '东海帝皇': '东海帝王', '富士奇迹': '富士奇石', '春乌拉拉': '春乌菈菈',
        '第一红宝石': '第一红宝', '艾尼斯风神': '艾尼风神', '菱钻奇宝': '菱奇宝',
        '葛城王牌': '葛城荣主', '超级小海湾': '超级溪流', '目白赖恩': '目白莱恩',
        '目白阿尔丹': '目白雅丹', '东瀛佐敦': '岛川乔丹', '真弓快车': '阿斯顿真弓',
        '天狼星象征': '克里斯象征', '摩耶重炮': '重炮',
    }
    return FIX.get(name, name)


def resolve_character(query: str):
    """模糊匹配角色. 返回 character dict (含 events) 或 None."""
    d = _load_raw()
    if d is None:
        return None
    q = query.strip()
    for c in d['characters']:
        if c['name'] == q or q in c.get('card_names', []):
            return c
    for c in d['characters']:
        if q in c['name'] or any(q in cn for cn in c.get('card_names', [])):
            return c
    for c in d['characters']:
        if c['name'] in q:
            return c
    return None


def load_events(name: str):
    """返回角色的事件列表. 每个事件含 subpage/event_type/meta/options."""
    c = resolve_character(name)
    return c['events'] if c else None


def events_with_options(name: str):
    """只返回有选项的事件 (event_type='有分支' 且 options 非空)."""
    evs = load_events(name)
    if evs is None:
        return None
    return [e for e in evs if e.get('options')]


def find_event(name: str, event_name: str):
    """按简中名/繁中名/日文名查找事件."""
    evs = load_events(name)
    if evs is None:
        return None
    q = event_name.strip()
    for e in evs:
        meta = e.get('meta', {})
        if q in (meta.get('简中名', ''), meta.get('繁中名', ''),
                 meta.get('事件名', ''), meta.get('中文名', '')):
            return e
    # subpage 包含
    for e in evs:
        if q in e.get('subpage', ''):
            return e
    return None


def event_summary(name: str):
    """事件统计."""
    evs = load_events(name)
    if evs is None:
        return None
    from collections import Counter
    by_type = Counter(e.get('event_type', '') for e in evs)
    by_owner = Counter(e.get('meta', {}).get('事件所属', '') for e in evs)
    with_opts = sum(1 for e in evs if e.get('options'))
    return {
        'total': len(evs),
        'with_options': with_opts,
        'by_type': dict(by_type),
        'by_owner': dict(by_owner),
    }


def main():
    args = sys.argv[1:]
    d = _load_raw()
    if d is None:
        print('chara_events.json 未生成. 运行 tools/build_chara_events.py 先抓取.')
        return 1
    if not args:
        print(f"chara_events: {d['meta']['chara_count']} chars, {d['meta']['event_count']} events")
        print(f"usage: {sys.argv[0]} <角色名> [--detail 事件名] [--summary]")
        return 0
    name = args[0]
    if '--summary' in args:
        s = event_summary(name)
        if s is None:
            print(f'未找到角色: {name}')
            return 1
        print(f'{name} 事件统计: {s["total"]} 总数, {s["with_options"]} 有选项')
        print(f'  按类型: {s["by_type"]}')
        print(f'  按所属: {s["by_owner"]}')
        return 0
    if '--detail' in args:
        i = args.index('--detail')
        ev_name = args[i + 1] if i + 1 < len(args) else ''
        e = find_event(name, ev_name)
        if e is None:
            print(f'未找到事件: {ev_name}')
            return 1
        m = e.get('meta', {})
        print(f"事件: {m.get('简中名') or m.get('事件名','?')}")
        print(f"  日文名: {m.get('事件名','')}  繁中名: {m.get('繁中名','')}")
        print(f"  所属: {m.get('事件所属','')}  类型: {e.get('event_type','')}")
        print(f"  关联技能: {m.get('关联技能','')}")
        print(f"  选项 ({len(e.get('options',[]))} 个):")
        for j, o in enumerate(e.get('options', []), 1):
            print(f"    [{j}] {o['option']}")
            print(f"        效果: {o['effect_cn'] or o['effect']}")
        return 0
    # 默认: 列出全部事件
    evs = load_events(name)
    if evs is None:
        print(f'未找到角色: {name}')
        return 1
    print(f'{name} 事件列表 ({len(evs)} 个):')
    for e in evs:
        m = e.get('meta', {})
        cn = m.get('简中名', '') or m.get('事件名', '?')
        owner = m.get('事件所属', '?')
        opts = len(e.get('options', []))
        tag = f' [{opts}选项]' if opts else ''
        print(f"  - {cn}  ({owner}){tag}")


if __name__ == '__main__':
    sys.exit(main())
