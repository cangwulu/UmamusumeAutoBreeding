# -*- coding: utf-8 -*-
"""update_assets.py — 国服更新后的一键数据刷新（马娘 / 协助卡 / 派生资产）。

背景
----
项目的数据资产分三层：
  1. BWIKI 抓取（国服实时源，需联网）：马娘本体(成长率/适性)、协助卡、技能、
     角色事件、育成目标、通用事件、比赛
  2. 上游 pretty-derby 拉取（马娘/卡 -> 自带技能归属的唯一来源）
  3. 构建/聚合（把 1/2 的原始产物加工成运行时 JSON + 名称索引）

国服更新（出新马娘/新协助卡/新技能）后，按本脚本编排的顺序重跑即可刷新全部。

用法：
    python tools/update_assets.py                 # 全量刷新
    python tools/update_assets.py --chars-only    # 只刷马娘线
    python tools/update_assets.py --cards-only    # 只刷协助卡线
    python tools/update_assets.py --dry-run       # 只打印将执行哪些步骤
    python tools/update_assets.py --no-images     # 跳过图片下载（体积大）

流程编排（按依赖序；每个步骤的产物会在末尾打印尺寸/条数便于核对）：

[马娘线]  马娘本体 + 技能归属 + 育成目标 + 角色事件 + 名称索引
[协助卡线] 协助卡本体 + 协助卡事件(urarawin 合并) + 名称索引
[通用]    上游缓存(技能归属源) + 事件库/技能库 + 图片 + 比赛等

各步骤实现都直接 subprocess 调用 tools/ 下已有脚本，保证与手工跑完全一致。
"""

import argparse
import datetime
import os
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
DATA = os.path.join(ROOT, "resource", "umamusume", "data")
PY = sys.executable


# ---------------------------------------------------------------- 步骤表

# 每步: (名字, 脚本, 参数, 关键产物, 说明)
# 产物的"条数检查"在 run() 里按 meta/顶层键尽力而为，缺省 None 跳过
STEPS = {
    # ---- 通用：上游缓存（多脚本的输入） ----
    "upstream": [
        ("拉取上游 db.json + zh_CN.json", "fetch_upstream.py", [],
         "tools/.cache/db.json", "pretty-derby 源；马娘技能归属/译名的唯一输入"),
    ],
    # ---- 马娘线 ----
    "chars": [
        ("抓取马娘本体(成长率/适性)", "fetch_bwiki_extra.py",
         ["--no-events"], "character_bwiki.json",
         "BWIKI 简中赛马娘一览；含 成长率 + 距离/场地/跑法适应性"),
        ("抓取马娘育成目标", "build_chara_targets.py",
         [], "chara_targets.json",
         "BWIKI 角色总页的育成目标比赛表"),
        ("构建马娘自带技能归属", "build_chara_skills.py",
         [], "chara_skills.json",
         "db.json players -> 固有/觉醒/初始技能；吃 upstream"),
        ("补形态日文名", "enrich_chara_skills_jp.py",
         [], "chara_skills.json",
         "给每张卡补 card_jp，按名对齐形态"),
        ("抓取角色育成事件", "build_chara_events.py",
         [], "chara_events.json",
         "SMW 子页 + 有分支事件选项（简中名↔日文名桥接源）"),
    ],
    # ---- 协助卡线 ----
    "cards": [
        ("抓取协助卡本体", "fetch_support_cards.py",
         [], "support_card_bwiki.json",
         "BWIKI 简中协助卡图鉴/一览；316 卡含类型与 jp_name"),
        ("集成 urarawin 协助卡事件", "integrate_urarawin.py",
         ["--build"], "support_events.json",
         "从上级目录 UmaMusumeLibrary.json 提取 283 卡/757 事件"),
    ],
    # ---- 派生聚合（马娘/协助卡都依赖） ----
    # 注意顺序：build_event_db 全量重建 event_db（会覆盖任何手工/合并补丁），
    # 所以 urarawin 独有事件的合并必须在它之后跑（merge 是增量补丁）。
    "derived": [
        ("构建事件库 + 技能库", "build_event_db.py",
         [], "event_db.json",
         "db.json events -> 中文事件库；全量重建，勿在其后依赖旧补丁"),
        ("urarawin 独有协助卡事件并入事件库", "merge_urarawin_support_events.py",
         [], "event_db.json",
         "补 build_event_db 未收录的 urarawin 协助卡事件（幂等，须在重建后跑）"),
        ("重建名称索引", "build_name_index.py",
         [], "name_index.json",
         "聚合 马娘/形态/卡/技能/事件/比赛 全部译名 -> resolver"),
    ],
    # ---- 图片（可选，体积大） ----
    "images": [
        ("抓取马娘头像/协助卡图鉴图片", "fetch_game_images.py",
         [], "chara_icon/", "本地图片档；CDN 直连下载(WAF 坑已处理)"),
    ],
}

# 模式 -> 执行顺序（键为 STEPS 组名）
MODES = {
    "all": ["upstream", "chars", "cards", "derived", "images"],
    "chars": ["upstream", "chars", "derived"],
    "cards": ["cards", "derived"],
}


# ---------------------------------------------------------------- 工具


def _size_of(rel_path: str):
    """产物相对 tools/ 或 resource/umamusume/data/ 路径的尺寸/条数摘要。"""
    cands = [
        os.path.join(TOOLS, rel_path),
        os.path.join(DATA, rel_path),
    ]
    for p in cands:
        if os.path.isfile(p):
            try:
                import json
                with open(p, encoding="utf-8") as f:
                    obj = json.load(f)
                if isinstance(obj, dict):
                    n = len(obj.get("events") or obj.get("characters")
                            or obj.get("cards") or obj.get("skills")
                            or obj.get("players") or obj.get("races")
                            or obj.get("by_key") or [])
                    return "%s (%s 条)" % (p, n) if n else p
                if isinstance(obj, list):
                    return "%s (%d 条)" % (p, len(obj))
            except Exception:
                pass
            return "%s (%.1f KB)" % (p, os.path.getsize(p) / 1024)
    return rel_path + "  (未生成?)"


def _run(cmd: list, name: str, dry: bool) -> bool:
    """跑一个子脚本；返回成功与否。dry-run 只打印。"""
    rel = cmd[0]
    full = [PY, os.path.join(TOOLS, rel)] + cmd[1:]
    if dry:
        print("  [dry] %s" % " ".join(full))
        return True
    print("\n>>> %s" % name)
    print("    %s" % " ".join(full))
    try:
        proc = subprocess.run(full, cwd=ROOT, timeout=600)
        if proc.returncode != 0:
            print("  [失败] %s (exit=%d)" % (rel, proc.returncode))
            return False
        return True
    except FileNotFoundError:
        print("  [缺失] %s 脚本不存在，跳过" % rel)
        return True
    except subprocess.TimeoutExpired:
        print("  [超时] %s (>600s)，跳过" % rel)
        return False


# ---------------------------------------------------------------- 主流程


def main():
    ap = argparse.ArgumentParser(
        description="国服更新后的数据一键刷新（马娘/协助卡/派生资产）")
    ap.add_argument("--chars-only", action="store_true", help="只刷马娘线")
    ap.add_argument("--cards-only", action="store_true", help="只刷协助卡线")
    ap.add_argument("--no-images", action="store_true", help="跳过图片下载")
    ap.add_argument("--dry-run", action="store_true", help="只打印步骤不执行")
    ap.add_argument("--no-backup", action="store_true",
                    help="不自动备份将被覆盖的 JSON（默认备份到 data/.bak/）")
    args = ap.parse_args()

    # 决定执行顺序
    if args.chars_only and args.cards_only:
        print("[错误] --chars-only 与 --cards-only 不能同时用；要全量就都不加")
        return 2
    if args.chars_only:
        order = MODES["chars"]
    elif args.cards_only:
        order = MODES["cards"]
    else:
        order = MODES["all"]
    if args.no_images and "images" in order:
        order = [g for g in order if g != "images"]

    # 备份将被覆盖的运行时 JSON（马娘/协助卡相关产物）
    if not args.no_backup and not args.dry_run:
        bak = os.path.join(DATA, ".bak")
        os.makedirs(bak, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        for rel in ("character_bwiki.json", "chara_targets.json",
                    "chara_skills.json", "chara_events.json",
                    "support_card_bwiki.json", "support_events.json",
                    "event_db.json", "skill_db.json", "name_index.json",
                    "event_bwiki.json", "skill_bwiki.json",
                    "race_bwiki.json", "affinity.json"):
            src = os.path.join(DATA, rel)
            if os.path.isfile(src):
                dst = os.path.join(bak, "%s.%s" % (rel, stamp))
                try:
                    import shutil
                    shutil.copy(src, dst)
                except Exception:
                    pass
        print("[备份] 数据快照 -> %s" % bak)

    print("=" * 64)
    print(" 数据刷新 · %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(" 模式: %s" % (" / ".join(order)))
    print("=" * 64)

    failed = []
    for grp in order:
        print("\n## 阶段 [%s]" % grp)
        for name, script, args_, prod, note in STEPS[grp]:
            print("  · %s -- 产物 %s" % (name, prod))
            if not args.dry_run:
                print("    (%s)" % note)
            ok = _run([script] + args_, name, args.dry_run)
            if not ok:
                failed.append(script)
                if grp in ("upstream",) and not args.dry_run:
                    print("  ⚠ 上游拉取失败——后续依赖它的步骤可能拿到旧数据")
                    return 1

    # 汇总
    print("\n" + "=" * 64)
    if args.dry_run:
        print(" dry-run 完成：以上步骤将按序执行（依赖 upstream 的先拉上游）")
    elif failed:
        print(" 完成，但以下步骤失败：%s" % ", ".join(failed))
        print(" 可重跑同一命令；产物已备份在 resource/umamusume/data/.bak/")
        return 1
    else:
        print(" 全部完成 ✅ 产物核对：")
        for grp in order:
            for _n, _s, _a, prod, _note in STEPS[grp]:
                if prod:
                    print("   %-34s %s" % (prod, _size_of(prod)))
        print("\n 提醒：若出了新技能/新事件名，建议跑一遍回归确认解析无退化：")
        print("   python tools/regress_name_resolver.py")
        print("   python tests/test_name_index_alias.py")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
