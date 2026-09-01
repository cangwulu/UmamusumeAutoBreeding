"""历战赛程路线生成器。

基于 race_bwiki.json（全量比赛时间表）+ character_bwiki.json（角色适性），
按时间槽贪心生成推荐赛程路线，用于养种马历战规划。

规则（编码自 strategy_integrated.md C 层攻略共识）：
- 每个半月份（年/月/前后半）是一个比赛槽，同槽只能跑一场；
- 粉丝门槛为硬约束：假设全部夺冠，粉丝 = Σfan_reward 单调递增；
- 候选打分 = 等级权重(G1≫G2>G3>OP) × 适性契合(场地+距离)；
- 节奏模式：max=全历战（有合适比赛就跑）；rest:N=每 N 连跑后歇一个有赛的槽；
- 同一场比赛多场次（如天王奖春秋）按不同赛次分别计数，胜鞍去重按 race id。

已知局限（使用时注意）：
- 游戏内"目标比赛"是强制的，实际执行时路线需与目标比赛合并；
- 假设全胜（历战养种马的前提是属性碾压低年级赛）；
- 不模拟体力/心情，休息节奏由模式参数近似。

用法：
    python module/umamusume/asset/route_planner.py 特别周
    python module/umamusume/asset/route_planner.py 小栗帽 --mode rest:2 --min-grade G3
"""
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_DATA_DIR = os.path.join(_PROJECT_ROOT, 'resource', 'umamusume', 'data')


def load_races() -> List[dict]:
    with open(os.path.join(_DATA_DIR, 'race_bwiki.json'), encoding='utf-8') as f:
        return json.load(f)['races']

GRADE_VALUE = {'G1': 1000, 'G2': 300, 'G3': 100, 'OP': 30, 'Pre-OP': 10}
GRADE_ORDER = ['Pre-OP', 'OP', 'G3', 'G2', 'G1']          # 升序
LETTER_SCORE = {'S': 9, 'A': 8, 'B': 7, 'C': 6, 'D': 5, 'E': 4, 'F': 3, 'G': 2}
_LETTER_RANK = {v: i for i, v in enumerate('SGFEDCBA')}    # G=0 ... S=7

_half_key = {'前': 0, '后': 1}


def load_characters() -> List[dict]:
    with open(os.path.join(_DATA_DIR, 'character_bwiki.json'), encoding='utf-8') as f:
        return json.load(f)['characters']


def resolve_character(name: str, characters: Optional[List[dict]] = None) -> Optional[dict]:
    """按名字找角色（card_name 或本名精确/包含匹配）。歧义时返回 None 并打印候选。"""
    characters = characters or load_characters()
    exact = [c for c in characters if c['name'] == name or c['card_name'] == name]
    if len(exact) == 1:
        return exact[0]
    contains = [c for c in characters if name in c['name'] or name in c['card_name']]
    if len(contains) == 1:
        return contains[0]
    if contains:
        print('歧义，请用完整名：')
        for c in contains[:8]:
            print(' ', c['card_name'])
    return None


def _adapt_map(char: dict) -> Tuple[Dict[str, int], Dict[str, int]]:
    """返回 (场地适性分, 距离适性分)。"""
    surface = {a['item']: LETTER_SCORE.get(a['grade'], 2) for a in char['adapt']['场地适应性']}
    dist = {a['item']: LETTER_SCORE.get(a['grade'], 2) for a in char['adapt']['距离适应性']}
    return surface, dist


def _fit(race: dict, surface: Dict[str, int], dist: Dict[str, int]) -> int:
    return surface.get(race['track'], 2) + dist.get(race['course'], 2)


def generate_route(char: dict, mode: str = 'max', min_grade: str = 'Pre-OP',
                   min_fit: int = 11, races: Optional[List[dict]] = None,
                   initial_fans: int = 3500) -> List[dict]:
    """生成历战路线。

    mode: 'max' 全历战 | 'rest:N' 每 N 连跑后歇一个有赛槽
    min_grade: 参赛等级下限（'Pre-OP'/'OP'/'G3'/'G2'/'G1'）
    min_fit: 适性契合下限（场地+距离字母分之和，8~18；默认 11 ≈ B+C）
    initial_fans: 出道战（新马战）后的起始粉丝，默认 3500（约一场新马赛夺冠收益）
    返回路线列表，每项含 slot/race/fit/fans_before/fans_after。
    """
    races = races or load_races()
    surface, dist = _adapt_map(char)
    min_grade_idx = GRADE_ORDER.index(min_grade) if min_grade in GRADE_ORDER else 0

    # 展开 (比赛, 场次) 并按时间排序
    entries = []
    for r in races:
        if r['grade'] not in GRADE_VALUE:
            continue
        for t in r['times']:
            entries.append((t['year'], t['month'], _half_key.get(t['half'], 0), t['half'], r))
    entries.sort(key=lambda e: (e[0], e[1], e[2]))

    # 按槽分组
    slots: List[Tuple[Tuple, List[Tuple]]] = []
    for e in entries:
        key = (e[0], e[1], e[2])
        if not slots or slots[-1][0] != key:
            slots.append((key, []))
        slots[-1][1].append((e[3], e[4]))

    fans = initial_fans
    route = []
    races_since_rest = 0
    rest_n = None
    if mode.startswith('rest:'):
        try:
            rest_n = int(mode.split(':')[1])
        except ValueError:
            rest_n = 2

    for key, cands in slots:
        # 该槽可选比赛：等级达标 + 适性达标 + 粉丝门槛达标
        ok = []
        for half, r in cands:
            if GRADE_ORDER.index(r['grade']) < min_grade_idx:
                continue
            fit = _fit(r, surface, dist)
            if fit < min_fit:
                continue
            need = r['fan_need'] or 0
            if need > fans:
                continue
            score = GRADE_VALUE[r['grade']] * fit / 16
            ok.append((score, fit, r['fan_reward'] or 0, half, r))
        if not ok:
            continue
        # 休息节奏：连跑满 N 场后，跳过一个有比赛的槽；但 G1 永不跳
        if rest_n is not None and races_since_rest >= rest_n:
            best_grade = max((x[4]['grade'] for x in ok), key=GRADE_ORDER.index)
            if best_grade != 'G1':
                races_since_rest = 0
                continue
        ok.sort(key=lambda x: (-x[0], -x[1], -x[2]))
        score, fit, _reward, half, r = ok[0]
        reward = r['fan_reward'] or 0
        route.append({
            'slot': '第%d年%d月%s半' % (key[0], key[1], half),
            'race': r,
            'fit': fit,
            'score': int(score),
            'fans_before': fans,
            'fans_after': fans + reward,
        })
        fans += reward
        races_since_rest += 1
    return route


def route_stats(route: List[dict]) -> dict:
    from collections import Counter
    grades = Counter(step['race']['grade'] for step in route)
    uniq = len({step['race']['id'] for step in route})
    fans = route[-1]['fans_after'] if route else 0
    g1_names = [step['race']['name'] for step in route if step['race']['grade'] == 'G1']
    return {
        'total': len(route),
        'grades': dict(grades),
        'unique_races': uniq,
        'final_fans': fans,
        'g1_list': g1_names,
    }


def _main(argv: List[str]) -> int:
    args = argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    name = args[0]
    mode = 'max'
    min_grade = 'Pre-OP'
    min_fit = 11
    initial_fans = 3500
    i = 1
    while i < len(args):
        if args[i] == '--mode':
            mode = args[i + 1]; i += 2
        elif args[i] == '--min-grade':
            min_grade = args[i + 1]; i += 2
        elif args[i] == '--min-fit':
            min_fit = int(args[i + 1]); i += 2
        elif args[i] == '--fans':
            initial_fans = int(args[i + 1]); i += 2
        else:
            i += 1

    char = resolve_character(name)
    if char is None:
        return 1
    route = generate_route(char, mode=mode, min_grade=min_grade, min_fit=min_fit,
                           initial_fans=initial_fans)
    st = route_stats(route)
    print('%s  [%s]' % (char['card_name'], mode))
    print('%-12s %-4s %-16s %-10s %6s  %8s' % ('时间', '等级', '比赛', '场地/距离', '契合', '粉丝'))
    for step in route:
        r = step['race']
        print('%-12s %-4s %-16s %-10s %6d  %6d→%d' % (
            step['slot'], r['grade'], r['name'],
            '%s%d' % (r['track'][0], r['distance']),
            step['fit'], step['fans_before'], step['fans_after']))
    print()
    print('合计 %d 场（G1×%d G2×%d G3×%d OP×%d）| 去重 %d 场（胜鞍候选）| 期末粉丝 %d' % (
        st['total'], st['grades'].get('G1', 0), st['grades'].get('G2', 0),
        st['grades'].get('G3', 0), st['grades'].get('OP', 0),
        st['unique_races'], st['final_fans']))
    if st['g1_list']:
        print('G1 路线：' + ' → '.join(st['g1_list']))
    return 0


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))
