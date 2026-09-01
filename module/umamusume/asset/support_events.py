# -*- coding: utf-8 -*-
"""支援卡事件查询（运行时**不联网**）——urarawin 数据库。

数据来源：
    resource/umamusume/data/support_events.json
    （tools/integrate_urarawin.py 从 urarawin.com UmaMusumeLibrary.json 提取）

urarawin 的支援卡事件覆盖 283 张卡（SSR:134 / SR:59 / R:90），
共 757 个事件，每个事件含 2~3 个选项 + 效果（日文+中文混排）。
角色名用日文（サイレンススズカ），通过 chara_skills.json 的 name_jp 做中日映射。

用法：
    from module.umamusume.asset.support_events import SupportEventDB
    db = SupportEventDB.get()
    db.search("铃鹿")              # 按角色名搜（中/日模糊）
    db.by_chara("サイレンススズカ") # 按日文名精确查
    db.by_card("［輝く景色の、その先に］サイレンススズカ")
    db.by_rarity("SSR")           # 按稀有度筛选
    db.event_summary("サイレンススズカ")  # 某角色所有支援卡的事件摘要

CLI：
    python module/umamusume/asset/support_events.py 铃鹿
    python module/umamusume/asset/support_events.py --ssr
    python module/umamusume/asset/support_events.py --card ［輝く景色の、その先に］サイレンススズカ
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

try:
    from bot.recog.fuzzy_match import cosine_sim
except ImportError:
    # 测试环境无 cv2 时，用简单的 difflib 替代
    import difflib
    def cosine_sim(a, b):
        return difflib.SequenceMatcher(None, a, b).ratio()

SUPPORT_EVENTS_PATH = "resource/umamusume/data/support_events.json"
CHARA_SKILLS_PATH = "resource/umamusume/data/chara_skills.json"


def _load_jp_cn_map():
    """从 chara_skills.json 加载 日文名→中文名 映射。"""
    mapping = {}
    try:
        with open(os.path.join(_PROJECT_ROOT, CHARA_SKILLS_PATH), encoding='utf-8') as f:
            data = json.load(f)
        for c in data.get('characters', []):
            jp = c.get('name_jp', '')
            cn = c.get('name', '')
            if jp and cn:
                mapping[jp] = cn
    except Exception:
        pass
    return mapping


class SupportCard(object):
    """一张支援卡及其事件。"""

    __slots__ = ('card_name', 'rarity', 'chara_name', 'chara_name_cn',
                 'card_title', 'event_count', 'events')

    def __init__(self, d, jp_cn_map=None):
        self.card_name = d.get('card_name', '')
        self.rarity = d.get('rarity', '')
        self.chara_name = d.get('chara_name', '')
        self.card_title = d.get('card_title', '')
        self.event_count = d.get('event_count', 0)
        self.events = d.get('events', [])
        self.chara_name_cn = ''
        if jp_cn_map and self.chara_name:
            self.chara_name_cn = jp_cn_map.get(self.chara_name, '')

    def __repr__(self):
        cn = self.chara_name_cn or self.chara_name
        return "SupportCard(%s [%s] %s %d事件)" % (
            self.rarity, cn, self.card_title, self.event_count)


class SupportEventDB(object):
    """支援卡事件库的懒加载单例。"""

    _inst = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst

    def __init__(self):
        with open(SUPPORT_EVENTS_PATH, encoding='utf-8') as f:
            data = json.load(f)
        self.meta = data['meta']
        self._jp_cn = _load_jp_cn_map()
        self.cards = [SupportCard(d, self._jp_cn) for d in data['cards']]
        # 索引
        self._by_card_name = {c.card_name: c for c in self.cards}
        self._by_chara = {}
        for c in self.cards:
            self._by_chara.setdefault(c.chara_name, []).append(c)
        # 中文名索引
        self._by_chara_cn = {}
        for c in self.cards:
            if c.chara_name_cn:
                self._by_chara_cn.setdefault(c.chara_name_cn, []).append(c)

    # ------------------------------------------------------------------ 查询

    def by_card(self, card_name):
        """按完整卡名精确查。"""
        return self._by_card_name.get(card_name)

    def by_chara(self, chara_name):
        """按日文角色名精确查该角色的所有支援卡。"""
        return self._by_chara.get(chara_name, [])

    def by_chara_cn(self, chara_name_cn):
        """按中文角色名精确查。"""
        return self._by_chara_cn.get(chara_name_cn, [])

    def by_rarity(self, rarity):
        """按稀有度筛选（SSR/SR/R）。"""
        return [c for c in self.cards if c.rarity == rarity]

    def search(self, query, top=10):
        """模糊搜索角色名（中日均可），返回 [(score, card), ...]。"""
        results = []
        for c in self.cards:
            # 精确匹配
            if query == c.chara_name or query == c.chara_name_cn:
                results.append((1.0, c))
                continue
            # 模糊匹配
            for name in (c.chara_name, c.chara_name_cn, c.card_title):
                if name:
                    s = cosine_sim(query, name)
                    if s > 0.3:
                        results.append((s, c))
                        break
        results.sort(key=lambda x: -x[0])
        return results[:top]

    def event_summary(self, chara_name):
        """某角色所有支援卡的事件摘要。"""
        cards = self.by_chara(chara_name) or self.by_chara_cn(chara_name)
        if not cards:
            cards = [c for s, c in self.search(chara_name)]
        summary = []
        for card in cards:
            for ev in card.events:
                summary.append({
                    'card': card.card_name,
                    'rarity': card.rarity,
                    'event_name': ev['event_name'],
                    'options': [(o['option'], o['effect']) for o in ev['options']],
                })
        return summary

    def all_chara_names(self):
        """所有角色名（日文+中文）集合。"""
        names = set()
        for c in self.cards:
            if c.chara_name:
                names.add(c.chara_name)
            if c.chara_name_cn:
                names.add(c.chara_name_cn)
        return sorted(names)

    def stats(self):
        """统计信息。"""
        from collections import Counter
        return {
            'total_cards': len(self.cards),
            'total_events': sum(c.event_count for c in self.cards),
            'by_rarity': dict(Counter(c.rarity for c in self.cards)),
            'by_chara': len(self._by_chara),
        }


def _main(argv):
    db = SupportEventDB.get()
    if not argv:
        print("用法: support_events.py <角色名> | --ssr | --sr | --r | "
              "--card <卡名> | --stats")
        print("\n统计:", db.stats())
        return 0

    if argv[0] == '--stats':
        print(json.dumps(db.stats(), ensure_ascii=False, indent=2))
        return 0

    if argv[0] == '--ssr':
        for c in db.by_rarity('SSR'):
            print(c)
        return 0

    if argv[0] == '--sr':
        for c in db.by_rarity('SR'):
            print(c)
        return 0

    if argv[0] == '--r':
        for c in db.by_rarity('R'):
            print(c)
        return 0

    if argv[0] == '--card':
        if len(argv) < 2:
            print("需要卡名参数")
            return 1
        card = db.by_card(argv[1])
        if not card:
            print("未找到卡: %s" % argv[1])
            return 1
        print(card)
        for ev in card.events:
            print("\n  事件: %s" % ev['event_name'])
            for opt in ev['options']:
                print("    选项: %s" % opt['option'])
                print("    效果: %s" % opt['effect'].replace('\n', ' | '))
        return 0

    # 按角色名搜索
    query = ' '.join(argv)
    results = db.search(query)
    if not results:
        print("未找到匹配 '%s'" % query)
        return 1

    print("搜索 '%s' 结果:" % query)
    for score, card in results:
        print(f"  [{score:.2f}] {card}")

    # 显示第一个的事件
    if results:
        card = results[0][1]
        print(f"\n{card.card_name} 的事件:")
        for ev in card.events:
            print(f"\n  {ev['event_name']}")
            for opt in ev['options']:
                print(f"    → {opt['option']}")
                print(f"      {opt['effect'].replace(chr(10), ' | ')}")
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
