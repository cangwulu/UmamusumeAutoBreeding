# -*- coding: utf-8 -*-
"""把上游 db.json 构建成「马娘 -> 自带技能」映射库。

输入（由 tools/fetch_upstream.py 拉取到 tools/.cache/）：
    db.json      游戏主数据（players 含 uniqueSkillList / initialSkillList / awakeningSkillList）
    zh_CN.json   中文译名表

输出（运行时直接读取，不联网）：
    resource/umamusume/data/chara_skills.json

数据模型：
    players 里每个条目 = 一个马娘「形态/卡」（同名角色有多个卡）。
      - uniqueSkillList   固有技能（角色级，同角色各卡相同）
      - awakeningSkillList 觉醒技能（角色级）
      - initialSkillList  初始技能（形态级，不同卡可能不同）
      - charaName         角色名（跨卡唯一），db_id 为形态 ID
    技能通过 id 哈希引用 db.skills；技能名/描述用 zh_CN.json 翻译，缺失回退日文。

产物按 charaName 聚合：一个角色一条，含角色级固有/觉醒技能 + 各形态的初始技能。

用法：
    python tools/build_chara_skills.py
"""
import json
import os
import sys
import time

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
CACHE_DIR = os.path.join(TOOLS_DIR, ".cache")
OUT_DIR = os.path.join(PROJECT_ROOT, "resource", "umamusume", "data")
OUT_PATH = os.path.join(OUT_DIR, "chara_skills.json")

SOURCE_REPO = "pretty-derby/pretty-derby.github.io"


def _has_kana(s):
    return any("\u3040" <= c <= "\u30ff" for c in s)


def load_cache():
    db_path = os.path.join(CACHE_DIR, "db.json")
    cn_path = os.path.join(CACHE_DIR, "zh_CN.json")
    missing = [p for p in (db_path, cn_path) if not os.path.isfile(p)]
    if missing:
        raise SystemExit(
            "缺少缓存文件：%s\n请先运行：python tools/fetch_upstream.py"
            % ", ".join(missing))
    with open(db_path, encoding="utf-8") as f:
        db = json.load(f)
    with open(cn_path, encoding="utf-8") as f:
        cn_raw = json.load(f)
    cn = {k: v for k, v in cn_raw.items() if isinstance(v, str)}
    return db, cn


def build(db, cn):
    # 技能 id -> 详情
    skill_by_id = {}
    for s in db.get("skills", []):
        sid = s.get("id")
        if not sid:
            continue
        jp = s.get("name") or ""
        cn_name = cn.get(jp, jp)
        if _has_kana(cn_name):
            cn_name = jp  # 未翻译，保留日文
        desc = s.get("describe") or ""
        desc_cn = cn.get(desc, desc)
        skill_by_id[sid] = {
            "id": sid,
            "name": cn_name.strip(),
            "name_jp": jp,
            "rare": s.get("rare") or "",
            "icon_id": s.get("icon_id"),
            "grade_value": s.get("grade_value"),
            "need_skill_point": s.get("need_skill_point"),
            "describe": desc_cn.strip() if desc_cn else "",
        }

    def resolve(ids):
        return [skill_by_id[i] for i in ids if i in skill_by_id]

    # 按 charaName 聚合
    charas = {}   # charaName_jp -> dict
    order = []
    for p in db.get("players", []):
        jp = p.get("charaName") or p.get("name") or ""
        if not jp:
            continue
        cn_name = cn.get(jp, jp)
        if _has_kana(cn_name):
            cn_name = jp
        entry = charas.get(jp)
        if entry is None:
            entry = {
                "name": cn_name.strip(),
                "name_jp": jp,
                "unique_skills": resolve(p.get("uniqueSkillList") or []),
                "awakening_skills": resolve(p.get("awakeningSkillList") or []),
                "cards": [],
            }
            charas[jp] = entry
            order.append(jp)
        entry["cards"].append({
            "card_name": cn.get(p.get("name"), p.get("name")),
            "db_id": p.get("db_id"),
            "initial_skills": resolve(p.get("initialSkillList") or []),
        })

    return [charas[k] for k in order]


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    db, cn = load_cache()
    print("已加载 db.json(%d players, %d skills)  zh_CN.json(%d 译名)"
          % (len(db.get("players", [])), len(db.get("skills", [])), len(cn)))

    chars = build(db, cn)
    n_uniq = sum(1 for c in chars if c["unique_skills"])
    n_awak = sum(1 for c in chars if c["awakening_skills"])
    print("角色数 %d（有固有技能 %d / 有觉醒技能 %d）" % (len(chars), n_uniq, n_awak))

    os.makedirs(OUT_DIR, exist_ok=True)
    out = {
        "meta": {
            "source_repo": SOURCE_REPO,
            "build_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "character_count": len(chars),
            "builder": "tools/build_chara_skills.py",
        },
        "characters": chars,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("已写出 -> %s" % os.path.relpath(OUT_PATH, PROJECT_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
