# -*- coding: utf-8 -*-
"""从上游拉取赛马娘原始数据到本地缓存。

数据源：pretty-derby/pretty-derby.github.io（原 wrrwrr111/pretty-derby，已改名）
  - public/db.json             游戏主数据（事件 / 技能 / 马娘 / 支援卡 / 赛事）
  - public/locales/zh_CN.json  中文译名表

设计要点：
  * 产物落在 tools/.cache/ 下，**运行时不联网** —— 只有本脚本需要网络。
  * 用 sha256 做增量判断，未变化则跳过下载。
  * 多镜像回退（raw.githubusercontent → jsDelivr），国内网络不稳时自动切换。

用法：
    python tools/fetch_upstream.py              增量拉取
    python tools/fetch_upstream.py --force      强制重下
    python tools/fetch_upstream.py --check      只检查缓存状态，不下载
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------- 路径常量

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(TOOLS_DIR, ".cache")
MANIFEST_PATH = os.path.join(CACHE_DIR, "manifest.json")

# 上游文件：本地文件名 -> 仓库内相对路径（镜像 URL 由 REPO_MIRRORS + 该路径拼出）
UPSTREAM_FILES = {
    "db.json": "public/db.json",
    "zh_CN.json": "public/locales/zh_CN.json",
}

REPO_MIRRORS = (
    "https://raw.githubusercontent.com/pretty-derby/pretty-derby.github.io/master",
    "https://cdn.jsdelivr.net/gh/pretty-derby/pretty-derby.github.io@master",
    "https://fastly.jsdelivr.net/gh/pretty-derby/pretty-derby.github.io@master",
)

USER_AGENT = "UmamusumeAutoTrainer/1.0 (+event-db-builder)"
TIMEOUT = 60


# ---------------------------------------------------------------- 工具函数


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest():
    if not os.path.isfile(MANIFEST_PATH):
        return {}
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def _save_manifest(manifest):
    _ensure_cache_dir()
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def _human(size):
    if size >= 1 << 20:
        return "%.2f MB" % (size / (1 << 20))
    if size >= 1 << 10:
        return "%.1f KB" % (size / (1 << 10))
    return "%d B" % size


def _download(url, dest, label):
    """流式下载，带进度显示。成功返回字节数，失败抛异常。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_print = 0.0
        with open(tmp, "wb") as out:
            while True:
                chunk = resp.read(1 << 18)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                now = time.perf_counter()
                if now - last_print > 0.2:
                    last_print = now
                    if total:
                        pct = done * 100.0 / total
                        sys.stdout.write(
                            "\r    %s  %5.1f%%  %s / %s"
                            % (label, pct, _human(done), _human(total))
                        )
                    else:
                        sys.stdout.write("\r    %s  %s" % (label, _human(done)))
                    sys.stdout.flush()
    os.replace(tmp, dest)
    sys.stdout.write("\r    %s  完成  %s%s\n" % (label, _human(done), " " * 20))
    sys.stdout.flush()
    return done


# ---------------------------------------------------------------- 主流程


def fetch_one(local_name, repo_rel_path, force=False):
    """拉取单个文件，返回 (状态, 详情)。状态 ∈ downloaded / unchanged / failed / skipped"""
    dest = os.path.join(CACHE_DIR, local_name)
    old_digest = _sha256(dest) if os.path.isfile(dest) else None

    if not force and old_digest is not None:
        return "unchanged", {
            "path": dest,
            "size": os.path.getsize(dest),
            "sha256": old_digest,
        }

    errors = []
    for mirror in REPO_MIRRORS:
        url = "%s/%s" % (mirror, repo_rel_path)
        print("  尝试 %s" % url)
        try:
            size = _download(url, dest, local_name)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
            errors.append("%s -> %s" % (mirror.split("//")[-1].split("/")[0], e))
            if os.path.exists(dest + ".part"):
                os.remove(dest + ".part")
            continue
        digest = _sha256(dest)
        changed = (digest != old_digest)
        return "downloaded", {
            "path": dest,
            "size": size,
            "sha256": digest,
            "url": url,
            "changed": changed,
        }

    return "failed", {"path": dest, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="拉取上游赛马娘数据库到本地缓存")
    parser.add_argument("--force", action="store_true", help="忽略本地缓存，强制重新下载")
    parser.add_argument("--check", action="store_true", help="只检查缓存状态，不下载")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    _ensure_cache_dir()
    manifest = _load_manifest()

    print("=" * 66)
    print("拉取上游数据库 -> %s" % CACHE_DIR)
    print("=" * 66)

    if args.check:
        for name in UPSTREAM_FILES:
            entry = manifest.get(name)
            path = os.path.join(CACHE_DIR, name)
            if entry and os.path.isfile(path):
                print("  %-12s 已缓存  %-10s  sha256=%s…"
                      % (name, _human(os.path.getsize(path)), entry["sha256"][:16]))
            else:
                print("  %-12s 缺失" % name)
        return 0

    failed = []
    for name, rel in UPSTREAM_FILES.items():
        print("\n[%s]" % name)
        status, info = fetch_one(name, rel, force=args.force)
        if status == "failed":
            print("  [失败] 所有镜像均不可用：")
            for e in info["errors"]:
                print("    - %s" % e)
            failed.append(name)
            continue

        if status == "unchanged":
            print("  已缓存且未指定 --force，跳过（%s）" % _human(info["size"]))
            if name not in manifest:
                manifest[name] = {
                    "size": info["size"],
                    "sha256": info["sha256"],
                    "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            continue

        manifest[name] = {
            "size": info["size"],
            "sha256": info["sha256"],
            "url": info["url"],
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        print("  %s  sha256=%s…" % (
            "有更新" if info.get("changed") else "无变化",
            info["sha256"][:16]))

    _save_manifest(manifest)

    print("\n" + "=" * 66)
    if failed:
        print("完成，但以下文件拉取失败：%s" % ", ".join(failed))
        print("（若已有旧缓存，可用旧数据继续构建）")
        return 1
    print("全部就绪。缓存目录：%s" % CACHE_DIR)
    print("下一步：python tools/build_event_db.py")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
