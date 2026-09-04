# -*- coding: utf-8 -*-
"""库存点选 + 大赛登记 + 规划 的 Web API (FastAPI router, 供 planning.html 使用).

端点半览:
  GET  /api/inventory        库存全量(state) —— 含图片文件名
  POST /api/inventory        按 idx 批量更新 拥有/星级/觉醒(卡:突破/等级)
  GET  /api/cup              已登记大赛情报 (未登记返回 null)
  POST /api/cup              保存大赛情报 (支持 --race 式比赛名查证)
  GET  /api/races?q=xxx      比赛名候选
  POST /api/plan             运行规划 -> 返回摘要 + 报告路径
  GET  /media/chara/{file}   马娘头像静态
  GET  /media/card/{file}    协助卡卡面静态
"""

import json
import os
import sys
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_PKG_DIR)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from module.umamusume.planning import inventory as inv_svc
from module.umamusume.planning import planner as plan_svc
from module.umamusume.planning.cup_info import (CONDITIONS, DIRECTIONS,
                                                DEFAULT_CUP_FILE, STYLES,
                                                SURFACES, WEATHERS, CupInfo)

router = APIRouter(prefix="/api")

# ---------- 图片文件名 -> URL 映射（启动时读 manifest, 失败静默降级无图） ----------
_CHARA_IMG_DIR = os.path.join(_PROJECT_ROOT, "resource", "umamusume", "chara_icon")
_CARD_IMG_DIR = os.path.join(_PROJECT_ROOT, "resource", "umamusume", "support_card_img")


def _load_chara_img_map() -> dict:
    """形态名 -> 图标文件名。按 manifest.roles[角色].images 与 CSV 形态顺序对齐。"""
    try:
        with open(os.path.join(_PROJECT_ROOT, "resource", "umamusume",
                               "chara_icon_manifest.json"), encoding="utf-8") as f:
            man = json.load(f)
    except Exception:
        return {}
    out = {}
    # 建立 角色 -> [(形态名?, 文件)]：manifest 无形态名, 由 CSV 顺序对齐, 故此处只存角色 images
    for role, info in man.get("roles", {}).items():
        imgs = info.get("images") or []
        if imgs:
            out[role] = imgs
    return out


def _load_card_img_map() -> dict:
    """卡名(含【】) -> 图片文件名。manifest 精确映射。"""
    try:
        with open(os.path.join(_PROJECT_ROOT, "resource", "umamusume",
                               "support_card_img_manifest.json"), encoding="utf-8") as f:
            man = json.load(f)
    except Exception:
        return {}
    out = {}
    for name, path in man.get("cards", {}).items():
        out[name] = os.path.basename(path)
    return out


_CHARA_ROLE_IMGS = _load_chara_img_map()
_CARD_IMG = _load_card_img_map()


def _decorate(state: dict) -> dict:
    """给 state 的每项附 img 字段(文件名, 可空)。"""
    role_count = {}
    for c in state.get("characters", []):
        role = c["role"]
        imgs = _CHARA_ROLE_IMGS.get(role) or []
        i = role_count.get(role, 0)
        role_count[role] = i + 1
        c["img"] = os.path.basename(imgs[i]) if i < len(imgs) else (os.path.basename(imgs[0]) if imgs else "")
    for c in state.get("cards", []):
        c["img"] = _CARD_IMG.get(c["name"], "")
    return state


# ---------- 模型 ----------
class CharaUpdate(BaseModel):
    idx: int
    own: bool = False
    star: int = 0
    awaken: int = 0


class CardUpdate(BaseModel):
    idx: int
    own: bool = False
    awaken: int = 0
    level: int = 0


class InventoryUpdate(BaseModel):
    characters: List[CharaUpdate] = []
    cards: List[CardUpdate] = []


class StudsSave(BaseModel):
    """种马登记：全量替换数据行（键=my_studs.csv 表头名）。"""
    rows: List[dict] = []


# ---------- 种马登记 ----------
@router.get("/studs")
def get_studs():
    """读已成品种马记录（供 planning 种马 tab 渲染）。"""
    return inv_svc.read_studs()


@router.post("/studs")
def save_studs(payload: StudsSave):
    """全量保存种马记录（示例行/空行自动剔除）。"""
    try:
        n = inv_svc.save_studs(payload.rows)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="保存失败: %s" % exc)
    return {"ok": True, "saved": n}


class CupPayload(BaseModel):
    race_name: str = ""
    venue: str = ""
    distance: int = 2000
    surface: str = "草地"
    direction: str = "右"
    weather: str = "晴"
    condition: str = "良"
    style: str = "差"
    note: str = ""


# ---------- 库存 ----------
@router.get("/inventory")
def get_inventory():
    try:
        state = inv_svc.read_state()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="读取库存失败: %s" % exc)
    _decorate(state)
    n_own_c = sum(1 for c in state["characters"] if c["own"])
    n_own_k = sum(1 for c in state["cards"] if c["own"])
    return {**state, "counts": {"characters": len(state["characters"]),
                                "cards": len(state["cards"]),
                                "own_characters": n_own_c,
                                "own_cards": n_own_k}}


@router.post("/inventory")
def update_inventory(payload: InventoryUpdate):
    try:
        res = inv_svc.apply_updates(
            [u.dict() for u in payload.characters],
            [u.dict() for u in payload.cards])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="保存失败: %s" % exc)
    return {"ok": True, "updated": res}


# ---------- 大赛情报 ----------
@router.get("/cup")
def get_cup():
    cup = CupInfo.load()
    return json.loads(json.dumps(cup.__dict__, ensure_ascii=False)) if cup else None


@router.post("/cup")
def save_cup(payload: CupPayload):
    cup = CupInfo(**payload.dict())
    errs = cup.validate()
    if errs:
        raise HTTPException(status_code=422, detail="; ".join(errs))
    cup.save()
    return {"ok": True, "cup": cup.__dict__}


@router.get("/races")
def query_races(q: str = "", grade: str = "", lang: str = ""):
    """比赛候选(联想/快选): [{name, venue, distance, surface, direction, grade, lang}]。

    q      —— 名字子串过滤（空=不过滤）
    grade  —— G1/G2/G3/OP/Pre-OP，按分级过滤（种马「跑过的G1」快选用 grade=G1）
    lang   —— cn/jp：只留国服名或日文名（同一场比赛两条记录，快选一般只想要 cn）
    注意：过滤必须在截断之前做，否则按名字排序会先切掉一半（日文名排在前面）。
    """
    try:
        from module.umamusume.asset import stud_planner
        data = stud_planner.load_json("race_bwiki.json")
    except Exception:
        return []
    out, seen = [], set()
    for r in data.get("races", []):
        cands = [(r.get("name"), "cn")]
        jp = r.get("jp_name")
        if jp and jp != r.get("name"):
            cands.append((jp, "jp"))
        for n, lg in cands:
            if not n or n in seen:
                continue
            seen.add(n)
            out.append({
                "name": n, "venue": r.get("venue", ""),
                "distance": int(r.get("distance") or 0),
                "surface": r.get("track", "草地"),
                "direction": r.get("direction", "右"),
                # 种马「跑过的G1」只应出 G1 —— 胜鞍分按现行规则只算 G1 重合
                "grade": r.get("grade", ""),
                "lang": lg,
            })
    if q:
        q = q.strip()
        out = [x for x in out if q in x["name"]]
    if grade:
        grade = grade.strip().upper()
        out = [x for x in out if str(x["grade"]).upper() == grade]
    if lang:
        lang = lang.strip().lower()
        out = [x for x in out if x["lang"] == lang]
    return sorted(out, key=lambda x: x["name"])[:500]


# ---------- 规划 ----------
class PlanPayload(BaseModel):
    top: int = 5
    style: str = ""   # 覆盖 cup.style


# ---------- 最近规划报告（hub 预览用） ----------
@router.get("/plan/recent")
def recent_plan(n: int = 6000):
    """找 my_inventory 下最近一次 Web 规划的 plan_*.md，返回摘要 + 尾部文本。"""
    import datetime

    inv_dir = os.path.join(_PROJECT_ROOT, "my_inventory")
    try:
        cands = []
        for f in os.listdir(inv_dir):
            if f.startswith("plan_") and f.endswith(".md"):
                p = os.path.join(inv_dir, f)
                cands.append((os.path.getmtime(p), p, f))
    except Exception:
        return {"exists": False, "reason": "无法读取 my_inventory"}
    if not cands:
        return {"exists": False}
    cands.sort(reverse=True)
    _, path, fname = cands[0]
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception as exc:
        return {"exists": False, "reason": str(exc)}
    return {"exists": True,
            "file": fname,
            "mtime": datetime.datetime.fromtimestamp(
                os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M"),
            "length": len(text),
            "md": text[-n:]}


@router.post("/plan")
def run_plan(payload: PlanPayload):
    cup = CupInfo.load()
    if cup is None:
        raise HTTPException(status_code=400,
                            detail="尚未登记大赛情报, 请先填大赛标签页")
    if payload.style:
        cup.style = payload.style
    try:
        out = plan_svc.plan(cup, top=payload.top)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="规划失败: %s" % exc)
    return {"ok": True,
            "summary": out["summary"],
            "md": _read_tail(out["md_path"]),
            "md_path": out["md_path"],
            "json_path": out["json_path"]}


def _read_tail(path: str, n: int = 2000) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()[-n:]
    except Exception:
        return ""


# ---------- 汇总状态（供 hub 入口页展示） ----------
@router.get("/status")
def get_status():
    """轻量聚合：数据资产规模 + 我的库存进度 + 大赛登记 + 版本。

    只读，任何文件缺失都静默降级（hub 页显示占位）。
    """
    import datetime

    data_dir = os.path.join(_PROJECT_ROOT, "resource", "umamusume", "data")

    def _size(name, key=None, sub=None):
        p = os.path.join(data_dir, name)
        try:
            with open(p, encoding="utf-8") as f:
                obj = json.load(f)
            if key:
                obj = obj.get(key, obj)
            if sub:
                obj = obj.get(sub, obj)
            if isinstance(obj, list):
                return len(obj)
            if isinstance(obj, dict):
                # by_key 类结构（name_index）
                if "by_key" in obj:
                    return len(obj["by_key"])
                return len(obj)
        except Exception:
            return None
        return None

    status = {
        "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "assets": {
            "event_db": _size("event_db.json", "events"),
            "support_events": _size("support_events.json", "cards"),
            "chara_events": _size("chara_events.json", "characters"),
            "chara_skills": _size("chara_skills.json", "characters"),
            "character_bwiki": _size("character_bwiki.json", "characters"),
            "support_cards": _size("support_card_bwiki.json", "cards"),
            "races": _size("race_bwiki.json", "races"),
            "name_index": _size("name_index.json"),
            "affinity": _size("affinity.json", "characters"),
        },
        "cup": None,
        "inventory": inv_svc.check(),
    }
    try:
        cup = CupInfo.load()
        if cup is not None:
            status["cup"] = {
                "label": cup.label() if hasattr(cup, "label") else str(cup),
                "updated_at": getattr(cup, "updated_at", ""),
            }
    except Exception:
        pass
    # 补充「拥有」计数（CSV 拥有(1/0) 列），供 hub 进度条
    try:
        import csv as _csv

        def _owned_csv(fname, own_col):
            p = os.path.join(_PROJECT_ROOT, "my_inventory", fname)
            if not os.path.isfile(p):
                return 0
            with open(p, encoding="utf-8-sig", newline="") as f:
                rows = list(_csv.reader(f))
            if len(rows) < 2:
                return 0
            hdr = rows[0]
            idx = next((i for i, h in enumerate(hdr) if "拥有" in h), own_col)
            n = 0
            for r in rows[1:]:
                if len(r) > idx and str(r[idx]).strip() in ("1", "是", "✓", "有"):
                    n += 1
            return n

        status["inventory"]["chara_owned"] = _owned_csv("my_characters.csv", 2)
        status["inventory"]["card_owned"] = _owned_csv("my_support_cards.csv", 4)
    except Exception:
        pass
    return status


# ---------- 库存模板 / 备份下载（hub 实用功能） ----------
_TEMPLATE_KIND = {"characters": "my_characters.csv",
                  "cards": "my_support_cards.csv",
                  "studs": "my_studs.csv"}


@router.get("/inventory/template")
def download_template(kind: str = "cards"):
    """下载一张「空白填报模板」CSV（不覆盖 my_inventory 里的真实文件）。

    生成到系统临时目录后以附件返回；kind ∈ characters/cards/studs。
    """
    import tempfile

    fname = _TEMPLATE_KIND.get(kind)
    if fname is None:
        raise HTTPException(status_code=400,
                            detail="kind 必须是 characters/cards/studs")
    tmp = tempfile.mkdtemp(prefix="uat_tpl_")
    try:
        sys.path.insert(0, os.path.join(_PROJECT_ROOT, "tools"))
        import gen_inventory_template as gen
        if kind == "characters":
            gen.gen_characters(tmp, force=True)
        elif kind == "cards":
            gen.gen_cards(tmp, force=True)
        else:
            gen.gen_studs(tmp, force=True)
        path = os.path.join(tmp, fname)
        if not os.path.isfile(path):
            raise HTTPException(status_code=500, detail="模板生成失败")
        return FileResponse(path, filename=fname,
                            media_type="text/csv")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="模板生成异常: %s" % exc)
    finally:
        try:
            sys.path.remove(os.path.join(_PROJECT_ROOT, "tools"))
        except ValueError:
            pass


@router.get("/inventory/backup")
def download_inventory():
    """把 my_inventory 下三个 CSV 打包返回（含已填内容，做本地备份）。"""
    import tempfile
    import zipfile

    inv_dir = os.path.join(_PROJECT_ROOT, "my_inventory")
    missing = [f for f in ("my_characters.csv", "my_support_cards.csv",
                           "my_studs.csv")
               if not os.path.isfile(os.path.join(inv_dir, f))]
    tmp = os.path.join(tempfile.mkdtemp(prefix="uat_bak_"),
                       "my_inventory.zip")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in ("my_characters.csv", "my_support_cards.csv",
                      "my_studs.csv"):
                p = os.path.join(inv_dir, f)
                if os.path.isfile(p):
                    zf.write(p, f)
        return FileResponse(tmp, filename="my_inventory.zip",
                            media_type="application/zip")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="打包失败: %s" % exc)


# ---------- 图片静态(限定文件名, 防穿越) ----------
def _safe_media(img_dir: str, file: str):
    if not file or ".." in file or "/" in file or "\\" in file:
        raise HTTPException(status_code=400, detail="bad file name")
    full = os.path.join(img_dir, file)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")
    return full


media_router = APIRouter()


@media_router.get("/chara/{file}")
def media_chara(file: str):
    return FileResponse(_safe_media(_CHARA_IMG_DIR, file))


@media_router.get("/card/{file}")
def media_card(file: str):
    return FileResponse(_safe_media(_CARD_IMG_DIR, file))
