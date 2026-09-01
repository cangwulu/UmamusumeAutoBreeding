# -*- coding: utf-8 -*-
"""把上游原始数据构建成本地事件库 / 技能库。

输入（由 tools/fetch_upstream.py 拉取到 tools/.cache/）：
    db.json      游戏主数据
    zh_CN.json   中文译名表

输出（运行时直接读取，**不联网**）：
    resource/umamusume/data/event_db.json   中文育成事件库
    resource/umamusume/data/skill_db.json   中文技能库（含评分，供技能排序）

设计要点：
  * 只保留**有中文译名**的事件名 —— 运行时的 OCR 输入是国服中文，
    日文事件名对检索毫无用处，留着只会增加误匹配。
  * 选项文本优先中文，缺失时回退日文（宁可保留也不要丢掉效果信息）。
  * 事件按 (name, choices) 合并，归属合并成列表 —— 同名事件在不同马娘/支援卡上
    选项往往一致，合并后体积更小，运行时按事件名检索也更省心。

用法：
    python tools/build_event_db.py
    python tools/build_event_db.py --legacy-score PATH/TO/UmaMusumeLibrary.json
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
CACHE_DIR = os.path.join(TOOLS_DIR, ".cache")
OUT_DIR = os.path.join(PROJECT_ROOT, "resource", "umamusume", "data")

EVENT_DB_PATH = os.path.join(OUT_DIR, "event_db.json")
SKILL_DB_PATH = os.path.join(OUT_DIR, "skill_db.json")

SOURCE_REPO = "pretty-derby/pretty-derby.github.io"

# 假名区间：译名若仍含假名，视为「未翻译」
def _has_kana(s):
    return any("\u3040" <= c <= "\u30ff" for c in s)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 加载


def load_cache():
    db_path = os.path.join(CACHE_DIR, "db.json")
    cn_path = os.path.join(CACHE_DIR, "zh_CN.json")
    missing = [p for p in (db_path, cn_path) if not os.path.isfile(p)]
    if missing:
        raise SystemExit(
            "缺少缓存文件：%s\n请先运行：python tools/fetch_upstream.py" % ", ".join(missing))

    with open(db_path, encoding="utf-8") as f:
        db = json.load(f)
    with open(cn_path, encoding="utf-8") as f:
        cn_raw = json.load(f)

    # zh_CN.json 里混有嵌套 dict 条目，只取「键 -> 字符串」的译名映射
    cn = {k: v for k, v in cn_raw.items() if isinstance(v, str)}
    return db, cn, _sha256(db_path), _sha256(cn_path)


def load_legacy_score(path):
    """从 UmaMusumeLibrary.json 抽取 技能日文名 -> Score。

    Score 藏在 Effect 字符串末尾（形如 '\\nScore:129'）。这份数据是 2023 年快照，
    覆盖率有限，仅作兜底：能关联上的用它的分，关联不上的留 null。
    """
    import re
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        lib = json.load(f)
    out = {}
    for items in lib.get("Skill", {}).values():
        for it in items:
            name = it.get("Name")
            effect = it.get("Effect") or ""
            if not name:
                continue
            m = re.search(r"Score\s*[:：]\s*(-?\d+)", effect)
            if m:
                out[name] = int(m.group(1))
    return out


# ---------------------------------------------------------------- 构建事件库


def build_events(db, cn):
    players = {p["id"]: p.get("name", "") for p in db.get("players", [])}
    supports = {s["id"]: (s.get("name", ""), s.get("rare", ""))
                for s in db.get("supports", [])}

    def owner_of(pid):
        if not pid:
            return "", "common", None
        if pid in players:
            return cn.get(players[pid], players[pid]), "player", None
        if pid in supports:
            name, rare = supports[pid]
            return cn.get(name, name), "support", (rare or None)
        return "", "common", None

    merged = {}          # (name_cn, choices_key) -> event dict
    stat = Counter()

    for ev in db.get("events", []):
        stat["total"] += 1
        name_jp = ev.get("name") or ""
        if not name_jp:
            stat["no_name"] += 1
            continue

        name_cn = cn.get(name_jp)
        if not name_cn or _has_kana(name_cn):
            stat["name_not_translated"] += 1
            continue
        name_cn = name_cn.strip()

        raw_choices = ev.get("choiceList") or []
        if not raw_choices:
            stat["no_choice"] += 1
            continue

        choices = []
        for i, ch in enumerate(raw_choices):
            if not isinstance(ch, (list, tuple)) or len(ch) < 1:
                continue
            opt_jp = ch[0] if isinstance(ch[0], str) else ""
            opt_cn = cn.get(opt_jp)
            if not opt_cn or _has_kana(opt_cn):
                opt_cn = opt_jp
                stat["option_not_translated"] += 1
            else:
                stat["option_translated"] += 1
            effects = ch[1] if len(ch) > 1 and isinstance(ch[1], list) else []
            choices.append({
                "i": i,
                "text": opt_cn.strip(),
                "text_jp": opt_jp,
                "effects": effects,
            })

        if not choices:
            stat["no_choice"] += 1
            continue

        owner_name, owner_type, owner_rare = owner_of(ev.get("pid"))
        key = (name_cn, json.dumps([c["text"] for c in choices], ensure_ascii=False))
        if key in merged:
            entry = merged[key]
            if owner_name and owner_name not in entry["owners"]:
                entry["owners"].append(owner_name)
            stat["merged"] += 1
        else:
            merged[key] = {
                "id": ev.get("id", ""),
                "name": name_cn,
                "name_jp": name_jp,
                "owner_type": owner_type,
                "owner_rare": owner_rare,
                "owners": [owner_name] if owner_name else [],
                "choices": choices,
            }
            stat["kept"] += 1

    events = list(merged.values())
    events.sort(key=lambda e: (e["name"], e["owner_type"]))
    return events, stat


def build_skills(db, cn, legacy_score):
    skills = []
    stat = Counter()
    for s in db.get("skills", []):
        stat["total"] += 1
        jp = s.get("name") or ""
        if not jp:
            continue
        cn_name = cn.get(jp)
        if not cn_name or _has_kana(cn_name):
            cn_name = jp
            stat["name_not_translated"] += 1
        else:
            stat["name_translated"] += 1

        describe = s.get("describe") or ""
        describe_cn = cn.get(describe, describe) if describe else ""

        score = legacy_score.get(jp)
        if score is not None:
            stat["score_from_legacy"] += 1
        else:
            stat["score_missing"] += 1

        skills.append({
            "id": s.get("id", ""),
            "name": cn_name.strip(),
            "name_jp": jp,
            "rare": s.get("rare") or "",
            "rarity": s.get("rarity"),
            "ability_value": s.get("ability_value"),
            "describe": describe_cn,
            "score": score,
        })
    skills.sort(key=lambda s: s["name"])
    return skills, stat


# ---------------------------------------------------------------- 主流程


def main():
    parser = argparse.ArgumentParser(description="构建本地事件库 / 技能库")
    parser.add_argument("--legacy-score", metavar="PATH",
                        help="可选：UmaMusumeLibrary.json 路径，用于补全技能 Score")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    print("=" * 66)
    print("构建本地事件库 / 技能库")
    print("=" * 66)

    db, cn, db_hash, cn_hash = load_cache()
    print("\n已加载缓存：db.json(%d 事件, %d 技能)  zh_CN.json(%d 译名)"
          % (len(db.get("events", [])), len(db.get("skills", [])), len(cn)))

    legacy_score = {}
    if args.legacy_score:
        legacy_score = load_legacy_score(args.legacy_score)
        print("已加载旧版技能评分：%d 条" % len(legacy_score))

    print("\n--- 构建事件库 ---")
    events, ev_stat = build_events(db, cn)
    n_opt = ev_stat["option_translated"] + ev_stat["option_not_translated"]
    print("  上游事件总数      %6d" % ev_stat["total"])
    print("  事件名无中文译名  %6d  (已剔除)" % ev_stat["name_not_translated"])
    print("  无选项            %6d  (已剔除)" % ev_stat["no_choice"])
    print("  合并重复条目      %6d" % ev_stat["merged"])
    print("  最终事件条目      %6d" % len(events))
    if n_opt:
        print("  选项中文覆盖率    %5.1f%%  (%d/%d)"
              % (ev_stat["option_translated"] * 100.0 / n_opt,
                 ev_stat["option_translated"], n_opt))

    print("\n--- 构建技能库 ---")
    skills, sk_stat = build_skills(db, cn, legacy_score)
    print("  技能总数          %6d" % sk_stat["total"])
    print("  技能名中文译名    %6d" % sk_stat["name_translated"])
    print("  有 Score          %6d" % sk_stat["score_from_legacy"])

    os.makedirs(OUT_DIR, exist_ok=True)
    build_time = time.strftime("%Y-%m-%d %H:%M:%S")

    event_db = {
        "meta": {
            "source_repo": SOURCE_REPO,
            "source_db_sha256": db_hash,
            "source_cn_sha256": cn_hash,
            "upstream_update_time": db.get("updateTime", ""),
            "build_time": build_time,
            "event_count": len(events),
            "builder": "tools/build_event_db.py",
        },
        "events": events,
    }
    with open(EVENT_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(event_db, f, ensure_ascii=False, separators=(",", ":"))

    skill_db = {
        "meta": {
            "source_repo": SOURCE_REPO,
            "source_db_sha256": db_hash,
            "source_cn_sha256": cn_hash,
            "build_time": build_time,
            "skill_count": len(skills),
            "score_source": "UmaMusumeLibrary.json" if legacy_score else "",
            "builder": "tools/build_event_db.py",
        },
        "skills": skills,
    }
    with open(SKILL_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(skill_db, f, ensure_ascii=False, separators=(",", ":"))

    print("\n--- 产物 ---")
    for p in (EVENT_DB_PATH, SKILL_DB_PATH):
        print("  %-58s %s" % (os.path.relpath(p, PROJECT_ROOT), _human(os.path.getsize(p))))

    print("\n" + "=" * 66)
    print("完成。运行时读取这两个文件即可，无需联网。")
    print("=" * 66)
    return 0


def _human(size):
    if size >= 1 << 20:
        return "%.2f MB" % (size / (1 << 20))
    if size >= 1 << 10:
        return "%.1f KB" % (size / (1 << 10))
    return "%d B" % size


if __name__ == "__main__":
    sys.exit(main())
