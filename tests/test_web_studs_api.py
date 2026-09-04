# -*- coding: utf-8 -*-
"""种马 Web 登记：HTTP 接口 /api/studs 冒烟测试（不落真盘）。

运行：
  E:\\MINICONDA\\envs\\uat\\python.exe tests\\test_web_studs_api.py

注意：POST 会把数据写进 my_inventory/my_studs.csv，
      本测试通过替换 web_api.inv_svc 的 save_studs 指向临时目录来规避。
"""

import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAIL = 0
PASS = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL: " + msg)


from bot.server.handler import server  # noqa: E402
from module.umamusume.planning import web_api  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

paths = {r.path for r in server.routes}
check("/api/studs" in paths, "/api/studs 未注册到 app，实际含: %s" % sorted(p for p in paths if p.startswith("/api")))

client = TestClient(server)

# ---- GET（只读真实文件，安全）----
r = client.get("/api/studs")
check(r.status_code == 200, "GET /api/studs 状态码 %s" % r.status_code)
body = r.json()
check("rows" in body and "exists" in body, "GET 返回结构缺少 rows/exists: %s" % body)
print("  GET /api/studs -> exists=%s rows=%d" % (body.get("exists"), len(body.get("rows", []))))

# ---- POST（重定向到临时目录，绝不污染 my_inventory）----
tmp = tempfile.mkdtemp(prefix="uat_studs_api_")
_orig_save = web_api.inv_svc.save_studs
_orig_read = web_api.inv_svc.read_studs
try:
    web_api.inv_svc.save_studs = lambda rows, directory=None: _orig_save(rows, tmp)
    web_api.inv_svc.read_studs = lambda directory=None: _orig_read(tmp)

    payload = {"rows": [
        {"种马角色名": "目白麦昆", "速度": "1200", "耐力": "1000",
         "蓝因子(如:速度3星,耐力2星)": "耐力3星",
         "粉因子(如:中距离3星)": "长距离3星",
         "跑过的G1(逗号分隔)": "天皇赏(春),宝冢纪念", "备注": "smoke"},
        {"种马角色名": "  "},                 # 空名剔除
        {"种马角色名": "示例马娘"},            # 示例行剔除
    ]}
    r = client.post("/api/studs", json=payload)
    check(r.status_code == 200, "POST /api/studs 状态码 %s，body=%s" % (r.status_code, r.text[:200]))
    d = r.json()
    check(d.get("saved") == 1, "POST 应写入 1 行，实际 %r" % d)

    r2 = client.get("/api/studs")
    rows = r2.json()["rows"]
    check(len(rows) == 1 and rows[0]["种马角色名"] == "目白麦昆", "写后读回不一致: %s" % rows)
    check(rows[0]["跑过的G1(逗号分隔)"] == "天皇赏(春),宝冢纪念", "G1 字段往返丢失")

    # 非法载荷不应 500 崩溃掉服务（缺 rows 键 -> 默认空列表）
    r3 = client.post("/api/studs", json={})
    check(r3.status_code == 200 and r3.json().get("saved") == 0, "空载荷应 200 且 saved=0，实际 %s" % r3.text[:200])
finally:
    web_api.inv_svc.save_studs = _orig_save
    web_api.inv_svc.read_studs = _orig_read
    shutil.rmtree(tmp, ignore_errors=True)

print("PASS %d / FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
