# -*- coding: utf-8 -*-
"""三年完整赛程查询（运行时**不联网**）——初级年/经典级年/高级年。

数据来源：
    resource/umamusume/data/race_schedule.json
    （tools/build_race_schedule.py 从 NGA 帖子 tid=31058705 解析，
     与 race_bwiki.json 交叉比对后生成，316 条赛程记录）

赛程结构：
    初级年(第1年) 7~12月 — 出道战 + Junior OP/G2/G3/G1
    经典级年(第2年) 1~12月 — 经典三冠+大部分重赏
    高级年(第3年) 1~12月 — 春秋G1+帝王赏(高级年限定)

    同一场比赛可能在多个年份出现（如宝塚記念在第2年和第3年都有）。
    经典级1~5月的比赛在高级年不出现；高级年6月新增帝王赏。

用法：
    from module.umamusume.asset.race_schedule import ScheduleDB
    db = ScheduleDB.get()
    db.at(2, 4, '前')                    # 第2年4月前半月所有比赛
    db.at(2, 4, '前', grade='G1')        # 同上，只看G1
    db.at(3, 12, '后', grade='G1')       # 第3年12月后半月G1
    db.races_by_name('有馬記念')         # 按日文名查该比赛所有出现时间
    db.full_schedule(year=2)             # 第2年完整赛程
    db.grade_timeline('G1')              # 三年所有G1按时间排序
    db.available(2, 6, '前', fan=5000)   # 第2年6月前粉丝5000可跑的比赛

CLI：
    python module/umamusume/asset/race_schedule.py --year 2 --month 4 --half 前
    python module/umamusume/asset/race_schedule.py --g1
    python module/umamusume/asset/race_schedule.py --name 有馬記念
"""

import json
import os
import sys
import threading

# 项目根引导
_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

SCHEDULE_PATH = "resource/umamusume/data/race_schedule.json"

# 等级排序权重
_GRADE_ORDER = {'G1': 0, 'G2': 1, 'G3': 2, 'OP': 3, 'Pre-OP': 4, '出道': 5}


class SchedEntry(object):
    """一条赛程记录：某场比赛在某个时间点的出现。"""

    __slots__ = ('race_id', 'name_cn', 'name_jp', 'year', 'month', 'half',
                 'grade', 'venue', 'track', 'distance', 'direction', 'lane',
                 'dist_cat', 'fan_reward', 'fan_need')

    def __init__(self, d):
        for k in self.__slots__:
            setattr(self, k, d.get(k))

    def __repr__(self):
        cn = self.name_cn or self.name_jp
        return "Sched(%d年%d月%s %s %s %s%dm %s%s %s 粉丝+%s)" % (
            self.year, self.month, self.half, self.grade, cn,
            self.venue, self.distance, self.direction,
            self.lane or '', self.track, self.fan_reward)

    @property
    def full_direction(self):
        """完整方向描述：如 '右内'、'左外'、'直线'。"""
        if self.lane:
            return self.direction + self.lane
        return self.direction

    @property
    def time_label(self):
        """时间标签：'第2年4月前'。"""
        return "第%d年%d月%s" % (self.year, self.month, self.half)


class ScheduleDB(object):
    """三年赛程库的懒加载单例。"""

    _inst = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst

    def __init__(self):
        with open(SCHEDULE_PATH, encoding='utf-8') as f:
            data = json.load(f)
        self.meta = data['meta']
        self.entries = [SchedEntry(d) for d in data['schedule']]
        # 按日文名索引
        self._by_jp = {}
        for e in self.entries:
            self._by_jp.setdefault(e.name_jp, []).append(e)

    # ------------------------------------------------------------------ 查询

    def at(self, year, month, half=None, grade=None, track=None,
           venue=None, dist_cat=None):
        """指定年/月(/前|后半月)的所有比赛，按等级+时间排序。

        Args:
            year: 1/2/3（初级/经典/高级）
            month: 1~12
            half: '前'/'后'/None（None=该月全部）
            grade: 'G1'/'G2'/'G3'/'OP'/'Pre-OP'/'出道'/None
            track: '草地'/'泥地'/None
            venue: 场地名/None
            dist_cat: '短'/'マイル'/'中'/'长'/None

        Returns:
            list[SchedEntry]
        """
        out = [e for e in self.entries
               if e.year == year
               and e.month == month
               and (half is None or e.half == half)
               and (grade is None or e.grade == grade)
               and (track is None or e.track == track)
               and (venue is None or e.venue == venue)
               and (dist_cat is None or e.dist_cat == dist_cat)]
        out.sort(key=lambda e: (_GRADE_ORDER.get(e.grade, 9), e.race_id or 99999))
        return out

    def available(self, year, month, half=None, fan=0, **kwargs):
        """指定时间点 + 粉丝数可参加的比赛。

        fan_need 为 None 或 0 的比赛无门槛（OP/Pre-OP/出道）；
        有 fan_need 的需 fan >= fan_need。
        """
        races = self.at(year, month, half, **kwargs)
        return [e for e in races
                if not e.fan_need or fan >= e.fan_need]

    def full_schedule(self, year=None, grade=None):
        """完整赛程（可按年/等级筛），按时间排序。"""
        out = [e for e in self.entries
               if (year is None or e.year == year)
               and (grade is None or e.grade == grade)]
        out.sort(key=lambda e: (e.year, e.month, e.half != '前',
                                _GRADE_ORDER.get(e.grade, 9)))
        return out

    def grade_timeline(self, grade='G1'):
        """三年中某等级全部比赛的时间线。"""
        return self.full_schedule(grade=grade)

    def races_by_name(self, name_jp):
        """按日文名查该比赛在三年中所有出现的时间点。"""
        return sorted(self._by_jp.get(name_jp, []),
                      key=lambda e: (e.year, e.month, e.half != '前'))

    def races_by_cn_name(self, name_cn):
        """按简中名查该比赛在三年中所有出现的时间点。"""
        out = [e for e in self.entries if e.name_cn == name_cn]
        return sorted(out, key=lambda e: (e.year, e.month, e.half != '前'))

    def year_summary(self, year):
        """某年的比赛统计：按等级计数。"""
        from collections import Counter
        entries = [e for e in self.entries if e.year == year]
        return dict(Counter(e.grade for e in entries))

    def g1_timeline(self):
        """三年所有G1的时间线（快捷方法）。"""
        return self.grade_timeline('G1')


def _main(argv):
    db = ScheduleDB.get()
    if not argv:
        print("用法: race_schedule.py [--year Y --month M --half 前|后] "
              "[--grade G1] [--g1] [--name NAME] [--summary]")
        print("\n赛程统计:")
        for y in (1, 2, 3):
            print("  第%d年: %s" % (y, db.year_summary(y)))
        return 0

    if '--g1' in argv:
        for e in db.g1_timeline():
            print(e, '需%s粉丝' % (e.fan_need or '-'))
        return 0

    if '--name' in argv:
        idx = argv.index('--name')
        name = argv[idx + 1] if idx + 1 < len(argv) else ''
        entries = db.races_by_name(name)
        if not entries:
            entries = db.races_by_cn_name(name)
        if not entries:
            print('%s: 未找到' % name)
        else:
            for e in entries:
                print(e)
        return 0

    if '--summary' in argv:
        for y in (1, 2, 3):
            print("第%d年: %s" % (y, db.year_summary(y)))
        print("总条目: %d" % len(db.entries))
        return 0

    year = month = half = grade = None
    if '--year' in argv:
        year = int(argv[argv.index('--year') + 1])
    if '--month' in argv:
        month = int(argv[argv.index('--month') + 1])
    if '--half' in argv:
        half = argv[argv.index('--half') + 1]
    if '--grade' in argv:
        grade = argv[argv.index('--grade') + 1]

    if year and month:
        races = db.at(year, month, half, grade=grade)
        for e in races:
            print(e, '需%s粉丝' % (e.fan_need or '-'))
        print('\n共 %d 场' % len(races))
    elif year:
        for e in db.full_schedule(year=year, grade=grade):
            print(e)
    else:
        print("用法: race_schedule.py [--year Y --month M --half 前|后] "
              "[--grade G1] [--g1] [--name NAME]")
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
