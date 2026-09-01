# -*- coding: utf-8 -*-
"""
重建本地分支历史：把孤立根提交的 4 个 commit 移植到 origin/dev 之上。

背景
----
本机 feat/event-matching 分支的根提交 d46d700 是「孤立根提交」（无父提交，
把整个项目 601 个文件做成全新快照），与 GitHub 上的 origin/dev 没有共同祖先。
这会导致：
  - 无法快进推送到 dev
  - 强推会抹掉 dev 的历史
  - 即使推成独立分支，GitHub 上也无法开 PR 合回 dev

做法
----
用 git commit-tree 依次重放这 4 个 commit 的「树」，把父指针接到 origin/dev
上。相比 checkout + apply：
  - 完全不触碰工作树和索引（避免大批量文件检出被中断）
  - 保留原有 4 个 commit 的粒度、commit message、作者与提交时间

用法
----
  python tools/rebuild_history.py            # 预览（不写入）
  python tools/rebuild_history.py --apply    # 实际写入分支 ref
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
BASE = "21929f907eec7d6bea49c89385f36c78436268d8"  # origin/dev
COMMITS = [
    "d46d7008990f64ce9a1b009510146e26cb9904bc",
    "14e737230b7c4af0181bc11babc8cd063603204d",
    "a1c3eafc9d94bff6b3842c15d43a755d9222a342",
    "28ed8db557f29885b784be7456ca8d570617f45a",
]
BRANCH = "feat/event-matching"


def git(args, env=None, check=True):
    """运行 git 命令，返回 stdout（已去尾部换行）。"""
    full = dict(os.environ)
    if env:
        full.update(env)
    p = subprocess.run(
        ["git"] + args,
        cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=full,
    )
    if check and p.returncode != 0:
        raise RuntimeError("git %s 失败: %s" % (" ".join(args), p.stderr.strip()))
    return p.stdout.strip()


def meta(sha):
    """取出原 commit 的作者信息与完整 message。"""
    sep = "\x1f"
    out = git(["log", "-1", "--format=%an" + sep + "%ae" + sep + "%aI" + sep + "%cn"
               + sep + "%ce" + sep + "%cI" + sep + "%B", sha])
    name, email, adate, cname, cemail, cdate, msg = out.split(sep, 6)
    return {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_AUTHOR_DATE": adate,
        "GIT_COMMITTER_NAME": cname,
        "GIT_COMMITTER_EMAIL": cemail,
        "GIT_COMMITTER_DATE": cdate,
    }, msg.strip()


def main():
    apply_mode = "--apply" in sys.argv

    print("基线上游 : %s (origin/dev)" % BASE[:10])
    print("待移植   : %d 个 commit" % len(COMMITS))
    print("目标分支 : %s" % BRANCH)
    print("模式     : %s" % ("写入" if apply_mode else "预览（加 --apply 实际执行）"))
    print("-" * 60)

    parent = BASE
    results = []
    for sha in COMMITS:
        tree = git(["rev-parse", sha + "^{tree}"])
        env, msg = meta(sha)
        subject = msg.split("\n", 1)[0]
        new = git(["commit-tree", tree, "-p", parent, "-m", msg], env=env)
        results.append((sha[:10], new[:10], subject))
        print("  %s -> %s  %s" % (sha[:10], new[:10], subject))
        parent = new

    print("-" * 60)
    print("新分支头 : %s" % parent)
    print("完整 hash: %s" % git(["rev-parse", parent]))

    # 校验：新头与 origin/dev 的差异，应与原 HEAD 一致（53 个文件）
    n_old = len(git(["diff", "--name-only", BASE, "28ed8db557f29885b784be7456ca8d570617f45a"]).splitlines())
    n_new = len(git(["diff", "--name-only", BASE, parent]).splitlines())
    print("差异校验 : 原 HEAD vs dev = %d 个文件；新 HEAD vs dev = %d 个文件" % (n_old, n_new))
    if n_old != n_new:
        print("!! 文件数不一致，请检查后再写入")
        return 1

    # 内容校验：两次 diff 的路径集合必须完全相同
    old_set = set(git(["diff", "--name-only", BASE, "28ed8db557f29885b784be7456ca8d570617f45a"]).splitlines())
    new_set = set(git(["diff", "--name-only", BASE, parent]).splitlines())
    if old_set != new_set:
        print("!! 差异文件集合不一致：")
        print("   仅原HEAD有:", sorted(old_set - new_set)[:10])
        print("   仅新HEAD有:", sorted(new_set - old_set)[:10])
        return 1
    print("内容校验 : 通过（差异文件集合完全一致）")

    if not apply_mode:
        print("\n预览结束，未写入任何 ref。确认无误后加 --apply 执行。")
        return 0

    # 写入分支 ref（本机有 ref 不落盘的坑，用 update-ref + 校验）
    git(["update-ref", "refs/heads/" + BRANCH, parent])
    import time
    time.sleep(1)
    got = git(["rev-parse", "refs/heads/" + BRANCH], check=False)
    if got != git(["rev-parse", parent]):
        # 兜底：直接写 ref 文件
        ref_path = os.path.join(REPO, ".git", "refs", "heads", *BRANCH.split("/"))
        os.makedirs(os.path.dirname(ref_path), exist_ok=True)
        with open(ref_path, "w") as f:
            f.write(git(["rev-parse", parent]) + "\n")
        time.sleep(1)
        got = git(["rev-parse", "refs/heads/" + BRANCH], check=False)
        print("（已用直接写文件方式补 ref）")

    print("\n分支 %s 已指向 %s" % (BRANCH, got[:10]))
    print("提示：原孤立历史仍可通过 backup/event-matching-20260901 访问")
    return 0


if __name__ == "__main__":
    sys.exit(main())
