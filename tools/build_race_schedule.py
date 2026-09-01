# -*- coding: utf-8 -*-
"""解析 NGA 三年赛程文本 → 结构化 JSON，并与 race_bwiki.json 交叉比对。

NGA 原帖：hoshikaze（原项目作者）在 NGA 发布的完整三年赛程表。
数据格式：每个 section 有标题行（初级年/经典级年/高级年 + 月份范围），
section 内按 "X月前" / "X月后" 分组，每组下每行是一场 tab 分隔的比赛记录。

字段：比赛名 \t 类型 \t 位置 \t 赛道 \t 长度 \t 方向(1-2个) \t 长度分类 \t 粉丝值 \t [参加所需粉丝值]

方向列特殊处理：
  - 基本方向：右 / 左 / 直线
  - 可选附加：内 / 外（表示内圈/外圈赛道）
  解析时看方向后面紧跟的是 "内/外" 还是 "短/マイル/中/长"，
  前者则拆成 direction + lane，后者则 direction 无附加。

用法：
    python tools/build_race_schedule.py            # 解析 + 比对 + 输出
    python tools/build_race_schedule.py --verbose  # 详细输出
"""

import json
import os
import re
import sys
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'resource', 'umamusume', 'data')
NGA_TXT = os.path.join(DATA_DIR, 'race_schedule_nga.txt')
BWIKI_JSON = os.path.join(DATA_DIR, 'race_bwiki.json')
OUTPUT_JSON = os.path.join(DATA_DIR, 'race_schedule.json')

# ── 常量映射 ──────────────────────────────────────────────────────────────

# 年份映射：初级年=1, 经典级年=2, 高级年=3
YEAR_MAP = {
    '初级年': 1,
    '经典级年': 2,
    '高级年': 3,
}

# 方向基本值
DIR_BASIC = {'右', '左', '直线'}
# 附加方向（内圈/外圈）
DIR_LANE = {'内', '外'}
# 长度分类
DIST_CAT = {'短', 'マイル', '中', '长'}

# 赛道表面对照
TRACK_MAP = {
    '芝': '草地',
    'ダート': '泥地',
}

# 场地名中日对照（NGA 用简中/部分日文，BWIKI 用简中）
VENUE_FIX = {
    '东京': '东京',
    '函馆': '函馆',
    '中京': '中京',
    '新潟': '新潟',
    '小倉': '小仓',
    '小仓': '小仓',
    '札幌': '札幌',
    '阪神': '阪神',
    '中山': '中山',
    '京都': '京都',
    '福岛': '福岛',
    '大井': '大井',
}


def parse_nga_text(text):
    """解析 NGA 文本，返回 [{year, month, half, name, grade, venue, track,
    distance, direction, lane, dist_cat, fan_reward, fan_need}, ...]
    """
    races = []
    lines = text.strip().split('\n')

    current_year = None
    current_month = None
    current_half = None  # '前' or '后'

    # section 标题匹配（不要求空格，"高级年1~6月" 也匹配）
    section_re = re.compile(r'^(初级年|经典级年|高级年)')
    # 月份分组匹配
    month_re = re.compile(r'^(\d+)月(前|后)\b')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # section 标题
        m = section_re.match(line)
        if m:
            for key, val in YEAR_MAP.items():
                if line.startswith(key):
                    current_year = val
                    break
            i += 1
            continue

        # 月份分组
        m = month_re.match(line)
        if m:
            current_month = int(m.group(1))
            current_half = m.group(2)
            i += 1
            continue

        # 跳过分隔线、说明文字、空行
        if not line or line.startswith('—') or line.startswith('由于') \
                or line.startswith('经典级') or line.startswith('高级年') \
                or line.startswith('月份') or line.startswith('改动'):
            i += 1
            continue

        # 尝试解析比赛行（tab 分隔）
        # 有些行可能是多 tab 或空格分隔
        parts = re.split(r'\t+', line)
        if len(parts) < 2:
            # 尝试空格分隔（但名字里可能有空格，所以只在 tab 失败时用）
            parts = line.split()
            if len(parts) < 6:
                i += 1
                continue

        # 过滤掉空 part
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) < 6:
            i += 1
            continue

        # 解析：尝试提取比赛记录
        # 字段顺序：比赛名 | 类型 | 位置 | 赛道 | 长度 | 方向(1-2) | 长度分类 | 粉丝值 | [fan_need]
        race = parse_race_parts(parts)
        if race is None:
            i += 1
            continue

        race['year'] = current_year
        race['month'] = current_month
        race['half'] = current_half
        races.append(race)
        i += 1

    return races


def parse_race_parts(parts):
    """从 tab 分隔的 parts 列表解析一场比赛。

    标准列序：name | grade | venue | track | distance | direction(1-2) | dist_cat | fan_reward | [fan_need]

    但 NGA 原帖有缺列情况：
    - 10月后部分比赛缺 venue（如"スワンステークス GII 芝 1400 右 外 短 5900"）
    - 12月后部分比赛缺 dist_cat（如"キャラクシーステークス OP 阪神 ダート 1400 右 2200"）

    策略：用"赛道在 track_surface 集合"来定位 track 列，
    然后向前回推判断是否有 venue。
    """
    if len(parts) < 6:
        return None

    name = parts[0]
    grade = normalize_grade(parts[1])

    # 从位置 2 开始，找 track（芝/ダート）
    track_idx = None
    for idx in range(2, min(len(parts), 6)):
        if parts[idx] in TRACK_MAP:
            track_idx = idx
            break
    if track_idx is None:
        return None

    # venue = track_idx-1 如果 track_idx > 2，否则无 venue
    venue = ''
    if track_idx > 2:
        venue = parts[2]
    track_raw = parts[track_idx]

    # distance = track_idx + 1（必须是数字）
    dist_idx = track_idx + 1
    if dist_idx >= len(parts) or not parts[dist_idx].isdigit():
        return None
    distance = int(parts[dist_idx])

    # 长度后面是 方向(1-2) + 长度分类(可选) + 粉丝值(数字) + [fan_need(数字)]
    remaining = parts[dist_idx + 1:]

    if not remaining:
        return None
    direction = remaining[0]
    if direction not in DIR_BASIC:
        return None

    idx = 1
    lane = ''

    # 可选的 lane（内/外）
    if idx < len(remaining) and remaining[idx] in DIR_LANE:
        lane = remaining[idx]
        idx += 1

    # 长度分类（可选，NGA 有些比赛缺这列）
    dist_cat = ''
    if idx < len(remaining) and remaining[idx] in DIST_CAT:
        dist_cat = remaining[idx]
        idx += 1
    elif idx < len(remaining) and not remaining[idx].isdigit():
        # 非数字非内外的，当长度分类处理
        dist_cat = remaining[idx]
        idx += 1

    # 粉丝值
    fan_reward = 0
    if idx < len(remaining) and remaining[idx].isdigit():
        fan_reward = int(remaining[idx])
        idx += 1

    # 参加所需粉丝值（可选）
    fan_need = None
    if idx < len(remaining) and remaining[idx].isdigit():
        fan_need = int(remaining[idx])
        idx += 1

    track = TRACK_MAP.get(track_raw, track_raw)
    venue_cn = VENUE_FIX.get(venue, venue) if venue else ''

    # 如果缺 dist_cat，从 distance 推断
    if not dist_cat:
        if distance <= 1400:
            dist_cat = '短'
        elif distance <= 1800:
            dist_cat = 'マイル'
        elif distance <= 2800:
            dist_cat = '中'
        else:
            dist_cat = '长'

    return {
        'name_jp': name,
        'grade': grade,
        'venue': venue_cn,
        'venue_raw': venue,
        'track': track,
        'track_raw': track_raw,
        'distance': distance,
        'direction': direction,
        'lane': lane,
        'dist_cat': dist_cat,
        'fan_reward': fan_reward,
        'fan_need': fan_need,
    }


def normalize_grade(g):
    """统一等级写法：G1/G2/G3/OP/Pre-OP/出道"""
    g = g.strip()
    # G1 有时写作 GI
    if g in ('G1', 'GI'):
        return 'G1'
    if g in ('G2', 'GII'):
        return 'G2'
    if g in ('G3', 'GIII'):
        return 'G3'
    if g == 'Pre-OP':
        return 'Pre-OP'
    if g == 'OP':
        return 'OP'
    if g == '出道':
        return '出道'
    return g


def _normalize_name(s):
    """归一化比赛名用于匹配：全角括号→半角、去空格、统一賞/赏。"""
    s = s.replace('（', '(').replace('）', ')')
    s = s.replace('　', '').replace(' ', '')
    s = s.replace('賞', '赏')
    return s


def cross_reference(nga_races, bwiki_data):
    """将 NGA 比赛与 race_bwiki.json 交叉比对。

    返回:
      matched: [(nga_race, bwiki_race_dict), ...]
      nga_only: NGA 有但 BWIKI 没有的比赛
      bwiki_only: BWIKI 有但 NGA 没有的比赛（按 jp_name 判断）
      enhancements: 需要更新到 BWIKI 的字段 [(bwiki_id, field, old_val, new_val), ...]
    """
    # 建立 jp_name → bwiki_race 索引（原始 + 归一化）
    bwiki_by_jp = {}
    bwiki_by_norm = {}
    for r in bwiki_data['races']:
        jp = r.get('jp_name', '')
        if jp:
            bwiki_by_jp.setdefault(jp, []).append(r)
            norm = _normalize_name(jp)
            bwiki_by_norm.setdefault(norm, []).append(r)

    matched = []
    nga_only = []
    enhancements = []
    matched_bwiki_ids = set()

    for nr in nga_races:
        jp = nr['name_jp']
        candidates = bwiki_by_jp.get(jp, [])

        if not candidates:
            # 归一化匹配（全角/半角括号、賞/赏、去空格）
            norm = _normalize_name(jp)
            candidates = bwiki_by_norm.get(norm, [])

        if not candidates:
            # 去空格后包含匹配
            jp_ns = jp.replace(' ', '').replace('　', '')
            for bj, brs in bwiki_by_jp.items():
                bj_ns = bj.replace(' ', '').replace('　', '')
                if jp_ns == bj_ns:
                    candidates = brs
                    break

        if not candidates:
            # 归一化后包含匹配（处理 "日本ダービー 東京優駿" vs "東京優駿（日本ダービー）"）
            norm = _normalize_name(jp)
            for bn, brs in bwiki_by_norm.items():
                if norm in bn or bn in norm:
                    candidates = brs
                    break

        if not candidates:
            # 拆分空格后的部分匹配（"日本ダービー 東京優駿" → 尝试 "東京優駿" 和 "日本ダービー"）
            for part in jp.replace('　', ' ').split():
                part_norm = _normalize_name(part)
                if part_norm and part_norm in bwiki_by_norm:
                    candidates = bwiki_by_norm.get(part_norm, [])
                    if candidates:
                        break

        if candidates:
            # 取第一个（通常只有一场同名比赛）
            br = candidates[0]
            matched_bwiki_ids.add(br['id'])
            matched.append((nr, br))

            # 检查需要增强的字段
            # 1. lane (内/外)
            if nr['lane'] and not br.get('lane'):
                enhancements.append((br['id'], 'lane', br.get('lane', ''), nr['lane']))
            elif nr['lane'] and br.get('lane') and nr['lane'] != br.get('lane'):
                enhancements.append((br['id'], 'lane', br.get('lane', ''), nr['lane']))

            # 2. fan_need
            if nr['fan_need'] is not None:
                old_fn = br.get('fan_need')
                if not old_fn or old_fn == 0:
                    enhancements.append((br['id'], 'fan_need', old_fn, nr['fan_need']))

            # 3. 检查 direction 是否有内/外信息未记录
            # BWIKI 的 direction 只有 右/左/直线，lane 记录 内/外
            # NGA 的 direction 是基本方向，lane 是附加

        else:
            nga_only.append(nr)

    # BWIKI 有但 NGA 没有的
    bwiki_only = []
    for r in bwiki_data['races']:
        if r['id'] not in matched_bwiki_ids:
            bwiki_only.append(r)

    return matched, nga_only, bwiki_only, enhancements


def build_schedule_json(nga_races, matched, enhancements):
    """构建 race_schedule.json：三年完整赛程。"""
    # 将 NGA 比赛与 BWIKI ID 关联
    schedule = []
    for nr, br in matched:
        entry = {
            'race_id': br['id'],
            'name_cn': br['name'],
            'name_jp': nr['name_jp'],
            'year': nr['year'],
            'month': nr['month'],
            'half': nr['half'],
            'grade': nr['grade'],
            'venue': nr['venue'],
            'track': nr['track'],
            'distance': nr['distance'],
            'direction': nr['direction'],
            'lane': nr['lane'],
            'dist_cat': nr['dist_cat'],
            'fan_reward': nr['fan_reward'],
            'fan_need': nr['fan_need'],
        }
        schedule.append(entry)

    # NGA only 的比赛（无 BWIKI ID）
    for nr in [nr for nr in nga_races if not any(nr is m[0] for m in matched)]:
        entry = {
            'race_id': None,
            'name_cn': None,
            'name_jp': nr['name_jp'],
            'year': nr['year'],
            'month': nr['month'],
            'half': nr['half'],
            'grade': nr['grade'],
            'venue': nr['venue'],
            'track': nr['track'],
            'distance': nr['distance'],
            'direction': nr['direction'],
            'lane': nr['lane'],
            'dist_cat': nr['dist_cat'],
            'fan_reward': nr['fan_reward'],
            'fan_need': nr['fan_need'],
        }
        schedule.append(entry)

    # 按年→月→半月→等级排序
    grade_order = {'G1': 0, 'G2': 1, 'G3': 2, 'OP': 3, 'Pre-OP': 4, '出道': 5}
    schedule.sort(key=lambda r: (
        r['year'], r['month'], r['half'] != '前',
        grade_order.get(r['grade'], 9), r['race_id'] or 99999
    ))

    return {
        'meta': {
            'source': ['NGA:tid=31058705 (hoshikaze)', 'race_bwiki.json (交叉比对)'],
            'desc': '三年完整赛程表：初级年(7~12月) + 经典级年(1~12月) + 高级年(1~12月)',
            'total_entries': len(schedule),
            'matched_with_bwiki': len(matched),
            'nga_only': len([r for r in schedule if r['race_id'] is None]),
            'enhancements_applied': len(enhancements),
        },
        'schedule': schedule,
    }


def main():
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    # 1. 读 NGA 文本
    with open(NGA_TXT, encoding='utf-8') as f:
        text = f.read()

    # 2. 解析
    nga_races = parse_nga_text(text)
    print(f'[解析] NGA 赛程条目: {len(nga_races)}')

    # 按年份统计
    year_counts = Counter(r['year'] for r in nga_races)
    for y in sorted(year_counts):
        print(f'  第{y}年: {year_counts[y]} 场')

    # 按等级统计
    grade_counts = Counter(r['grade'] for r in nga_races)
    print('  等级分布:', dict(sorted(grade_counts.items(), key=lambda x: x[0])))

    # 3. 读 BWIKI JSON
    with open(BWIKI_JSON, encoding='utf-8') as f:
        bwiki_data = json.load(f)
    print(f'[比对] race_bwiki.json: {len(bwiki_data["races"])} 场')

    # 4. 交叉比对
    matched, nga_only, bwiki_only, enhancements = cross_reference(nga_races, bwiki_data)
    print(f'[比对] 匹配成功: {len(matched)}')
    print(f'[比对] NGA 独有: {len(nga_only)}')
    print(f'[比对] BWIKI 独有: {len(bwiki_only)}')
    print(f'[比对] 需增强字段: {len(enhancements)}')

    if verbose or len(nga_only) > 0:
        print('\n--- NGA 独有（BWIKI 无）---')
        for nr in nga_only:
            print(f'  {nr["name_jp"]} [{nr["grade"]}] {nr["venue"]} '
                  f'{nr["track"]} {nr["distance"]}m {nr["direction"]}'
                  f'{" "+nr["lane"] if nr["lane"] else ""} '
                  f'{nr["dist_cat"]} 粉丝+{nr["fan_reward"]}'
                  f' 需{nr["fan_need"] or "-"} '
                  f'(第{nr["year"]}年{nr["month"]}月{nr["half"]})')

    if verbose or len(enhancements) > 0:
        print('\n--- 需增强字段 ---')
        for bid, field, old, new in enhancements:
            print(f'  race_id={bid} {field}: {old!r} → {new!r}')

    if verbose and len(bwiki_only) > 0:
        print('\n--- BWIKI 独有（NGA 无，前20条）---')
        for br in bwiki_only[:20]:
            print(f'  [{br["id"]}] {br.get("jp_name","")} / {br["name"]} '
                  f'[{br.get("grade","")}] {br.get("venue","")}')

    # 5. 输出 race_schedule.json
    output = build_schedule_json(nga_races, matched, enhancements)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    print(f'\n[输出] {OUTPUT_JSON}')
    print(f'  总条目: {output["meta"]["total_entries"]}')
    print(f'  匹配 BWIKI: {output["meta"]["matched_with_bwiki"]}')
    print(f'  NGA 独有: {output["meta"]["nga_only"]}')

    # 6. 输出增强建议
    if enhancements:
        enh_file = os.path.join(DATA_DIR, 'race_bwiki_enhancements.json')
        enh_data = {
            'desc': 'NGA 赛程数据对 race_bwiki.json 的字段补全建议',
            'count': len(enhancements),
            'items': [
                {'race_id': bid, 'field': field, 'old_value': old, 'new_value': new}
                for bid, field, old, new in enhancements
            ]
        }
        with open(enh_file, 'w', encoding='utf-8') as f:
            json.dump(enh_data, f, ensure_ascii=False, indent=1)
        print(f'[输出] {enh_file} ({len(enhancements)} 条增强建议)')

    # 7. 可选：直接 patch race_bwiki.json
    if '--patch' in sys.argv:
        patched = 0
        for bid, field, old, new in enhancements:
            for r in bwiki_data['races']:
                if r['id'] == bid:
                    r[field] = new
                    patched += 1
                    break
        with open(BWIKI_JSON, 'w', encoding='utf-8') as f:
            json.dump(bwiki_data, f, ensure_ascii=False, indent=1)
        print(f'[patch] 已更新 {patched} 个字段到 race_bwiki.json')

    return 0


if __name__ == '__main__':
    sys.exit(main())
