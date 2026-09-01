# -*- coding: utf-8 -*-
"""用 agent-browser(无头 Chromium) 渲染 BWIKI 国服简体 wiki 页面，
绕过其 WAF(对 curl/wget 返回空 body)，抽取结构化表格数据。

为什么用浏览器而不是 curl：
    wiki.biligame.com/umamusume 对无浏览器指纹的客户端返回 0 字节 body
    (HTTP 200 + Content-Length 非空，但 body 为空)。WebFetch 能取但会截断大表，
    故用 agent-browser 渲染完整 DOM 后直接抽表格 HTML。

输出（运行时可直接读取，**不联网**）：
    resource/umamusume/data/skill_bwiki.json   简体技能库(评价分 + 技能数值)
    resource/umamusume/data/event_peak_bwiki.json  简体巅峰杯事件名(后续用于别名表)

用法：
    python tools/scrape_bwiki.py --page skill
    python tools/scrape_bwiki.py --page event_peak
    python tools/scrape_bwiki.py --page skill --merge     # 合并进 skill_db.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
OUT_DIR = os.path.join(PROJECT_ROOT, "resource", "umamusume", "data")

PAGES = {
    "skill": "https://wiki.biligame.com/umamusume/%E7%AE%80%E4%B8%AD%E6%8A%80%E8%83%BD%E9%80%9F%E6%9F%A5%E8%A1%A8",
    "event_peak": "https://wiki.biligame.com/umamusume/%E7%AE%80%E4%B8%AD%E5%B7%85%E5%B3%B0%E6%9D%AF%E4%BA%8B%E4%BB%B6%E4%B8%80%E8%A7%88",
    "chara": "https://wiki.biligame.com/umamusume/%E7%AE%80%E4%B8%AD%E8%B5%9B%E9%A9%AC%E5%A8%98%E4%B8%80%E8%A7%88",
}

# 目标表格表头关键字 -> 输出字段名（用“包含”匹配，兼容译名微调）
SKILL_HEADER_MAP = {
    "技能名": "name",
    "稀有度": "rarity",
    "技能描述": "desc",
    "技能类型": "type",
    "技能数值": "values",
    "持续时间": "duration",
    "评价分": "eval_score",
    "共需技能": "total_pt",
    "PT评价比": "pt_ratio",
    "触发条件": "trigger",
}

# 抽取最大表格 HTML 的 JS（WAF 只拦 body，DOM 里数据齐全，含被 JS 过滤隐藏的行）
_EXTRACT_JS = r"""
(() => {
  const tables = Array.from(document.querySelectorAll('table'));
  let best = null, bestRows = -1;
  for (const t of tables) {
    const rows = t.querySelectorAll('tr').length;
    if (rows > bestRows) { bestRows = rows; best = t; }
  }
  if (!best) return '';
  // 去掉脚本/样式噪音
  best.querySelectorAll('script,style').forEach(e => e.remove());
  return best.outerHTML;
})()
"""


def find_agent_browser():
    home = os.path.expanduser("~")
    # Windows 上 .bin/agent-browser 是 POSIX 脚本，subprocess 无法直接执行，
    # 必须走 node_modules/agent-browser/bin/ 下的原生 exe
    if sys.platform.startswith("win"):
        native = os.path.join(home, ".workbuddy", "binaries", "node",
                             "workspace", "node_modules", "agent-browser",
                             "bin", "agent-browser-win32-x64.exe")
        if os.path.isfile(native):
            return native
    cand = os.path.join(home, ".workbuddy", "binaries", "node",
                        "workspace", "node_modules", ".bin", "agent-browser")
    if os.path.isfile(cand):
        return cand
    p = shutil.which("agent-browser")
    if p:
        return p
    raise SystemExit("未找到 agent-browser，请先安装：npm install -g agent-browser")


AB = find_agent_browser()


def _ab(*args, timeout=180):
    return subprocess.run([AB, *args], capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="replace")


def render_largest_table_html(url, wait="networkidle"):
    """打开页面 -> 等待 -> 抽取最大表格 outerHTML。返回 (html, debug)。"""
    r = _ab("open", url)
    if r.returncode != 0:
        raise RuntimeError("agent-browser open 失败: " + (r.stderr or r.stdout)[-500:])
    # wait 可能永不 idle，失败就降级
    _ab("wait", "--load", wait, timeout=60)
    r = _ab("eval", _EXTRACT_JS, timeout=120)
    html = r.stdout.strip()
    if not html:
        raise RuntimeError("未取到表格 HTML。stderr=%s" % (r.stderr or "")[:500])
    return html


def _cell_texts(cell):
    """单元格内可能有多值（<br>/换行分隔），返回文本列表。"""
    # 以 <br> 作分隔
    for br in cell.find_all("br"):
        br.replace_with("\n")
    txt = cell.get_text("\n")
    parts = [p.strip() for p in txt.split("\n") if p.strip()]
    return parts


def _norm(s):
    return (s or "").replace(" ", "").replace("　", "").lower()


def parse_generic_table(html, header_map, required_key):
    """通用表格解析：按表头关键字映射到字段；多值单元格保留为列表。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    rows = table.find_all("tr")
    if not rows:
        return []

    # 找表头行：首个含已知表头的行
    header_cells = None
    header_idx = -1
    for i, tr in enumerate(rows):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        matched = [k for k in header_map if any(k in c for c in cells)]
        if matched:
            header_cells = cells
            header_idx = i
            break
    if header_cells is None:
        return []

    # 每个单元格 -> 对应字段（优先精确，其次包含）
    col_field = []
    for raw in header_cells:
        field = None
        for k, v in header_map.items():
            if raw == k or raw.endswith(k) or k in raw:
                field = v
                break
        col_field.append(field)

    out = []
    for tr in rows[header_idx + 1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < len(col_field):
            # 跳过明显异常行（如分组标题）
            if len(cells) <= 1:
                continue
        rec = {}
        for ci, field in enumerate(col_field):
            if field is None or ci >= len(cells):
                continue
            texts = _cell_texts(cells[ci])
            if len(texts) == 1:
                rec[field] = texts[0]
            else:
                rec[field] = texts
        if required_key in rec and rec[required_key]:
            out.append(rec)
    return out


def parse_skill(html):
    recs = parse_generic_table(html, SKILL_HEADER_MAP, "name")
    for r in recs:
        # 评价分/PT 数值化
        for num_field in ("eval_score", "total_pt", "pt_ratio", "duration"):
            v = r.get(num_field)
            if isinstance(v, str):
                try:
                    r[num_field] = float(v.replace(",", ""))
                except ValueError:
                    pass
    recs.sort(key=lambda r: _norm(r.get("name", "")))
    return recs


def merge_into_skill_db(bwiki_skills, skill_db_path):
    """把 BWIKI 的评价分/数值按 简体名 合并进现有 skill_db.json。
    返回 (合并后的skills, 命中数, 新增数)。"""
    if not os.path.isfile(skill_db_path):
        return bwiki_skills, 0, len(bwiki_skills)
    with open(skill_db_path, encoding="utf-8") as f:
        db = json.load(f)
    existing = {_norm(s.get("name", "")): s for s in db.get("skills", [])}

    hit = 0
    added = 0
    for b in bwiki_skills:
        key = _norm(b.get("name", ""))
        if not key:
            continue
        if key in existing:
            tgt = existing[key]
            tgt["eval_score_bwiki"] = b.get("eval_score")
            tgt["values_bwiki"] = b.get("values")
            tgt["trigger_bwiki"] = b.get("trigger")
            hit += 1
        else:
            # 国服专属技能 or 译名差异未命中，作为新条目补入
            db["skills"].append({
                "name": b.get("name"),
                "name_jp": "",
                "rarity": b.get("rarity"),
                "eval_score": b.get("eval_score"),
                "values_bwiki": b.get("values"),
                "trigger_bwiki": b.get("trigger"),
                "source": "bwiki",
            })
            added += 1
    db["skills"].sort(key=lambda s: _norm(s.get("name", "")))
    return db["skills"], hit, added


def main():
    ap = argparse.ArgumentParser(description="抓取 BWIKI 国服简体数据")
    ap.add_argument("--page", choices=list(PAGES), default="skill",
                    help="要抓取的页面")
    ap.add_argument("--merge", action="store_true",
                    help="把结果合并进已存在的 skill_db.json")
    ap.add_argument("--out", default=None, help="输出 JSON 路径(默认按 page 命名)")
    args = ap.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    url = PAGES[args.page]
    print("打开页面: %s" % url)
    html = render_largest_table_html(url)
    print("  取到表格 HTML: %d 字符" % len(html))

    if args.page == "skill":
        recs = parse_skill(html)
        out_name = args.out or os.path.join(OUT_DIR, "skill_bwiki.json")
        if args.merge:
            skill_db_path = os.path.join(OUT_DIR, "skill_db.json")
            skills, hit, added = merge_into_skill_db(recs, skill_db_path)
            with open(skill_db_path, "w", encoding="utf-8") as f:
                json.dump({"meta": {"merged_bwiki": True}, "skills": skills},
                          f, ensure_ascii=False, separators=(",", ":"))
            print("  合并进 skill_db.json: 命中 %d, 新增 %d" % (hit, added))
            out_name = skill_db_path
        else:
            data = {"meta": {"source": "wiki.biligame.com/umamusume 简中技能速查表",
                             "count": len(recs)}, "skills": recs}
            with open(out_name, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        print("  技能条目: %d  -> %s" % (len(recs), out_name))
    else:
        # 事件/角色页：暂只原样落盘供后续解析
        out_name = args.out or os.path.join(OUT_DIR, "%s_bwiki.json" % args.page)
        data = {"meta": {"source": url, "note": "原始抽取，待解析"}, "raw_html_len": len(html)}
        with open(out_name, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("  非技能页暂存: %s (len=%d)" % (out_name, len(html)))

    # 收尾：关闭浏览器 daemon
    _ab("close")
    print("完成。")


if __name__ == "__main__":
    main()
