# -*- coding: utf-8 -*-
"""比赛数据库查询（运行时**不联网**）——简中服权威译名。

数据来源：
    resource/umamusume/data/race_bwiki.json
    （tools/build_race_data.py 从 BWIKI「比赛」+「简中比赛」两页构建，313 场）

译名规则（用户约定）：
    **比赛译名以 BWIKI「简中比赛」页为准**（name_source=cn），
    「比赛」页（日服表）的 wiki 中文名与旧资料（race.csv）译名普遍不准——
    简中服 253 场比赛改名，如 高松宮記念→中京短途赛、安田纪念赛→东京英里赛、
    有马纪念赛→中山大奖赛、日本杯→全国杯、樱花赏→樱花奖。

别名体系：每场比赛可从 简中权威名 / 日文原名 / wiki旧中文名 / 繁译名 / race.csv 旧名
    任一别名查到，并返回权威简中名（`resolve`）。

用法：
    from module.umamusume.asset.race_bwiki import RaceDB
    db = RaceDB.get()
    db.resolve("有马纪念赛")            # -> Race(中山大奖赛)
    db.resolve("フェブラリーステークス") # -> Race(二月锦标赛)
    db.month_races(3, 4, half='后')     # 第三年4月后半月可跑的所有比赛
    db.grade_races('G1')                # 32 场 G1（按时间排序）
    db.cn_name("樱花赏")                # -> '樱花奖'

CLI：
    python module/umamusume/asset/race_bwiki.py 有马纪念赛
    python module/umamusume/asset/race_bwiki.py --month 3 4 后 --grade G1
    python module/umamusume/asset/race_bwiki.py --g1
"""

import json
import os
import sys
import threading

# 允许「直接跑脚本」而不只是被 import：把项目根塞进 sys.path。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from bot.recog.fuzzy_match import cosine_sim

RACE_BWIKI_PATH = "resource/umamusume/data/race_bwiki.json"

# 比赛名（3~8 字中文）模糊容错：先精确/别名，再 cosine 兜底。
_ACCEPT = 0.60


class Race(object):
    """一场比赛。字段见 race_bwiki.json；常用属性直读。"""

    __slots__ = ('id', 'name', 'name_source', 'jp_name', 'wiki_cn_name',
                 'tw_name', 'times', 'time_text', 'grade', 'venue', 'venue_jp',
                 'track', 'distance', 'course', 'direction', 'lane',
                 'fan_reward', 'fan_need', 'grade_pt', 'shop_pt', 'note',
                 'attrs', 'csv_ids')

    def __init__(self, d):
        for k in self.__slots__:
            setattr(self, k, d.get(k))

    def __repr__(self):
        return "Race(%d %s %s %s%dm %s %s)" % (
            self.id, self.name, self.grade, self.venue, self.distance,
            self.track, self.time_text)

    def available_at(self, year, month, half=None):
        """该比赛是否在 指定年/月(/前|后半月) 可跑。times 为空的行返回 False。"""
        for t in self.times or []:
            if t['year'] == year and t['month'] == month and \
                    (half is None or t['half'] == half):
                return True
        return False


class RaceDB(object):
    """比赛库的懒加载单例。"""

    _inst = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst

    def __init__(self):
        with open(RACE_BWIKI_PATH, encoding='utf-8') as f:
            data = json.load(f)
        self.meta = data['meta']
        self.races = [Race(d) for d in data['races']]
        self._by_id = {r.id: r for r in self.races}
        # 别名 → race（先注册权威名；冲突时权威名优先，其余别名带来源标记）
        self._alias = {}
        for r in self.races:
            self._alias.setdefault(r.name, r)
        for r in self.races:
            for a in (r.jp_name, r.wiki_cn_name, r.tw_name):
                if a and a not in self._alias:
                    self._alias[a] = r
            for cid in r.csv_ids or []:
                self._alias.setdefault('csv:%s' % cid, r)
        self._names = [r.name for r in self.races]

    # ------------------------------------------------------------------ 查询

    def by_id(self, race_id):
        return self._by_id.get(race_id)

    def by_csv_id(self, csv_id):
        """race.csv 的模板 id（如 1401）→ 权威比赛。"""
        r = self._alias.get('csv:%s' % csv_id)
        return r

    def resolve(self, name, accept=_ACCEPT):
        """任意已知译名（简中/日文/wiki中文/繁中）→ Race；找不到返回 None。"""
        r = self._alias.get(name)
        if r:
            return r
        # 模糊兜底：全量暴力 cosine（勿用 FuzzyIndex，见 affinity.py 同款教训）
        best, score = None, 0.0
        for n in self._names:
            s = cosine_sim(name, n)
            if s > score:
                best, score = n, s
        if best is not None and score >= accept:
            return self._alias[best]
        return None

    def cn_name(self, name):
        r = self.resolve(name)
        return r.name if r else None

    def search(self, name, top=5):
        """候选列表 [(权威名, cosine, Race)]，供人工确认。"""
        res = sorted(((cosine_sim(name, n), self._alias[n]) for n in self._names),
                     key=lambda x: -x[0])[:top]
        return [(r.name, s, r) for s, r in res]

    # ------------------------------------------------------------------ 赛程

    def month_races(self, year, month, half=None, grade=None, track=None,
                    course=None, venue=None):
        """某年某月（可再筛前后半月）可跑的全部比赛，按时间+等级排序。"""
        out = [r for r in self.races
               if r.available_at(year, month, half)
               and (grade is None or r.grade == grade)
               and (track is None or r.track == track)
               and (course is None or r.course == course)
               and (venue is None or r.venue == venue)]
        out.sort(key=lambda r: (r.grade not in ('G1',), r.grade, r.id))
        return out

    def grade_races(self, grade='G1'):
        """某等级全部比赛（按 时间→场地 排序），做历战赛程规划用。"""
        out = [r for r in self.races if r.grade == grade]
        out.sort(key=lambda r: (r.times[0]['year'], r.times[0]['month'],
                                r.times[0]['half'] != '前', r.venue, r.id)
                 if r.times else (9, 9, True, '', r.id))
        return out


def _main(argv):
    db = RaceDB.get()
    if not argv:
        print("用法: race_bwiki.py <比赛名> | --month <年> <月> [前|后] [--grade G1] "
              "| --g1 | --search <名>")
        return 0
    if argv[0] == '--g1':
        for r in db.grade_races('G1'):
            print(r, '粉丝+%s 需%s' % (r.fan_reward, r.fan_need))
        return 0
    if argv[0] == '--search':
        for name, s, r in db.search(argv[1] if len(argv) > 1 else ''):
            print('%.3f %s -> %s' % (s, name, r))
        return 0
    if argv[0] == '--month':
        year, month = int(argv[1]), int(argv[2])
        half = argv[3] if len(argv) > 3 else None
        grade = None
        if '--grade' in argv:
            grade = argv[argv.index('--grade') + 1]
        for r in db.month_races(year, month, half, grade=grade):
            print(r, '粉丝+%s 需%s' % (r.fan_reward, r.fan_need))
        return 0
    for a in argv:
        r = db.resolve(a)
        if r is None:
            print('%s: 未找到。候选:' % a)
            for name, s, rr in db.search(a):
                print('  %.3f %s' % (s, name))
        else:
            print(json.dumps({k: getattr(r, k) for k in Race.__slots__
                              if k != 'times'},
                             ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
