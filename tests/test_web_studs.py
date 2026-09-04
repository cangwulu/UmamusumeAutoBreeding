# -*- coding: utf-8 -*-
"""种马 Web 登记：inventory.read_studs / save_studs 往返测试。

运行：
  E:\\MINICONDA\\envs\\uat\\python.exe tests\\test_web_studs.py
覆盖：
  1) 模板表头与网页 STUD_KEYS 一致
  2) 保存剔除空名/示例行；读回字段无损
  3) 保存→读回→再保存 幂等
  4) 文件不存在时降级返回 exists=False
"""

import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module.umamusume.planning import inventory as inv  # noqa: E402

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL: " + msg)


# 1) 网页 planning.html 里的 STUD_KEYS 必须与模板表头逐字一致
WEB_KEYS = ["种马角色名", "速度", "耐力", "力量", "根性", "智力",
            "蓝因子(如:速度3星,耐力2星)", "粉因子(如:中距离3星)",
            "白因子技能(逗号分隔)", "绿因子(继承固有)", "跑过的G1(逗号分隔)", "备注"]
check(inv.STUD_HEADERS == WEB_KEYS, "STUD_HEADERS 与 planning.html STUD_KEYS 不一致")

tmp = tempfile.mkdtemp(prefix="uat_studs_")
try:
    p = os.path.join(tmp, "my_studs.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        f.write(",".join('"%s"' % h for h in inv.STUD_HEADERS) + "\n")

    rows = [
        {"种马角色名": "黄金船", "速度": "1100", "耐力": "900", "力量": "800", "根性": "400",
         "智力": "700", "蓝因子(如:速度3星,耐力2星)": "耐力3星,速度2星",
         "粉因子(如:中距离3星)": "中距离3星", "白因子技能(逗号分隔)": "地固,弧线教授",
         "绿因子(继承固有)": "黄金船固有", "跑过的G1(逗号分隔)": "皋月奖,日本德比", "备注": "A"},
        {"种马角色名": "   ", "速度": "1"},              # 空名 -> 跳过
        {"种马角色名": ""},                                # 空名 -> 跳过
        {"种马角色名": "示例马娘", "速度": "1"},           # 模板示例行 -> 跳过
        {"种马角色名": "特别周", "速度": "1000", "备注": "B"},
    ]
    n = inv.save_studs(rows, tmp)
    check(n == 2, "save_studs 应写入 2 行，实际 %d" % n)

    back = inv.read_studs(tmp)
    check(back.get("exists") is True, "read_studs.exists 应为 True")
    check(len(back["rows"]) == 2, "read_studs 应读回 2 行，实际 %d" % len(back["rows"]))

    r0 = back["rows"][0]
    check(r0["种马角色名"] == "黄金船", "首行角色名错误: %s" % r0["种马角色名"])
    check(r0["蓝因子(如:速度3星,耐力2星)"] == "耐力3星,速度2星", "蓝因子往返丢失")
    check(r0["粉因子(如:中距离3星)"] == "中距离3星", "粉因子往返丢失")
    check(r0["白因子技能(逗号分隔)"] == "地固,弧线教授", "白因子往返丢失")
    check(r0["绿因子(继承固有)"] == "黄金船固有", "绿因子往返丢失")
    check(r0["跑过的G1(逗号分隔)"] == "皋月奖,日本德比", "G1 往返丢失")
    check(r0["速度"] == "1100" and r0["根性"] == "400", "属性往返丢失")
    check(set(r0.keys()) == set(inv.STUD_HEADERS), "读回的键集与表头不一致")
    check(back["rows"][1]["种马角色名"] == "特别周", "次行角色名错误")

    # 3) 幂等
    n2 = inv.save_studs(back["rows"], tmp)
    check(n2 == 2, "二次保存应为 2 行，实际 %d" % n2)
    check(inv.read_studs(tmp)["rows"] == back["rows"], "保存→读回不幂等")

    # 4) 全空输入 -> 只剩表头
    check(inv.save_studs([], tmp) == 0, "空输入应写 0 行")
    check(inv.read_studs(tmp)["rows"] == [], "全清后应无数据行")

    # 5) 缺文件降级
    empty = tempfile.mkdtemp(prefix="uat_studs_empty_")
    try:
        check(inv.read_studs(empty) == {"exists": False, "rows": []}, "缺文件应降级 exists=False")
    finally:
        shutil.rmtree(empty, ignore_errors=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("PASS %d / FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
