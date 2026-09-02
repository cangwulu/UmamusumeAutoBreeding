#!/usr/bin/env python3
# DEPRECATED (2026-09-02, M0): 本项目已切换到 origin/main 主干工作流，
# 而本脚本要求当前分支为 dev(旧 fork 工作流遗留), 会持续误报。
# run.ps1 已不再调用本脚本; 保留文件仅避免外部引用断裂。可安全删除。
import os
import sys
import shutil
import subprocess
import colorama

colorama.init()

RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
GRAY   = "\033[90m"
RESET  = "\033[0m"

def print_error(msg):
    print(f"{RED}{msg}{RESET}")


def print_warn(msg):
    print(f"{YELLOW}{msg}{RESET}")


def print_info(msg):
    print(f"{GREEN}{msg}{RESET}")


def print_ok(msg):
    print(f"{GRAY}{msg}{RESET}")


def run_cmd(cmd):
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()


def main():
    # 1. 检查 git 是否存在
    if shutil.which("git") is None:
        print_info("[INFO] 没有安装git, 跳过更新检查步骤")
        sys.exit(1)

    # 2. 检查 .git 目录（是否为 Git 仓库）
    if not os.path.isdir(".git"):
        print_info("[INFO] 当前路径不是git仓库, 跳过更新检查步骤")
        sys.exit(1)

    # 3. 获取当前分支并检查是否为 dev
    try:
        current_branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    except subprocess.CalledProcessError as e:
        print_error(f"[ERROR] 无法获取当前分支, 错误: {e.output}")
        sys.exit(1)

    if current_branch != "dev":
        print_warn(f"[WARN] 你当前的分支是 {current_branch}, 可能不是最新更新, 建议执行 'git checkout dev' 切换至发布分支")
        sys.exit(1)

    # 4. 拉取远程更新信息 (优先上游 upstream, 失败则回退到 fork 的 origin)
    remote_ref = "upstream/dev"
    try:
        subprocess.check_call(["git", "fetch", "upstream"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print_warn("[WARN] 获取上游仓库(upstream)信息失败, 改为从 fork(origin) 检查")
        remote_ref = "origin/dev"
        try:
            subprocess.check_call(["git", "fetch", "origin"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            print_warn(f"[WARN] 获取远程仓库信息失败: {e}, 跳过更新检查")
            sys.exit(1)

    # 5. 对比本地与远程: 本地落后多少个提交
    try:
        local_hash  = run_cmd(["git", "rev-parse", "HEAD"])
        behind_count = int(run_cmd(["git", "rev-list", "--count", "HEAD.." + remote_ref]))
    except subprocess.CalledProcessError as e:
        print_error(f"[ERROR] 获取commit信息错误: {e.output}, 退出更新检查")
        sys.exit(1)

    # 6. 对比并提示
    if behind_count > 0:
        if remote_ref == "upstream/dev":
            print_info(f"\n[INFO] 检查到更新(落后 {behind_count} 个提交), 请执行 'git pull upstream dev' 获取最新版本")
        else:
            print_info(f"\n[INFO] 检查到更新(落后 {behind_count} 个提交, 基于 fork 的 origin), 请执行 'git pull origin dev' 获取最新版本")
    else:
        print_ok("\n[OK] 当前文件为最新版本")


if __name__ == "__main__":
    main()
