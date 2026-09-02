# 重构实施计划：面向「大赛情报 → 种马规划 → 人工确认 → 自动育成」闭环

> 创建：2026-09-02 ｜ 依据：`.workbuddy/reports/codebase-review-2026-09-02.md` 全仓体检 + 用户拍板选型
> 当前 HEAD：`a637b05`（feat/event-matching，跟踪 origin/main）
> 状态：**待用户确认后从 M0 开工**

## 0. 目标（用户原话的工程化翻译）

把下述流程变成一条可重复执行的命令链：
**输入** = 我的种马库存（`my_inventory/my_studs.csv`）+ 我拥有的马娘/协助卡（`my_characters.csv` / `my_support_cards.csv`）+ 下次大赛的赛道情报（比赛名或 7 项赛道参数）
**输出** = 自动产出的逐代种马养成计划 → **我逐匹确认** → 自动育成 → **结局自动回填库存**（多代迭代）

## 1. 已拍板选型（用户已确认）

| 项 | 决定 |
|---|---|
| Python | **3.11.x**（paddlepaddle==2.6.2 支持 cp38–cp312；3.10 于 2026-10 EOL；本机默认 3.13 不支持 paddle 2.6.2） |
| OCR | **保持 PaddleOCR + paddlepaddle==2.6.2**，不换引擎（识别链路已调好，是最贵资产） |
| 大赛输入 | **CLI 优先**（`--race 比赛名` 或 7 项赛道参数），持久化 `cup_info.json`；Web 表单后补（共用同一份文件） |
| 依赖锁定 | requirements.in（意图）+ pip-tools 锁全量 requirements.txt；venv 项目内 |
| 前端 | 主路不依赖；删 electron；vite 升级放 M3 |
| 下一步 | 本文档作为实施计划，用户确认后执行 |

## 2. 目标架构（收敛，不推翻）

```
┌─ 数据资产层（asset/* + name_resolver）:只依赖 数据+纯算法 ─ 本次仅清耦合
│
├─ 领域服务层（新增 module/umamusume/planning/，三个薄服务，先 CLI 后 HTTP）
│    CupService        大赛情报录入/查证/持久化 → my_inventory/cup_info.json
│    InventoryService  CSV 读写/校验/模板生成/结局回填
│    PlanService       planner 库化: plan(cup, inventory) -> plan.json
│
├─ 执行层（现有 cultivate/scheduler/target_build 改造）
│    target_build.run() 消费 plan.json 条目（替换 raise NotImplementedError）
│    cultivate 局末解析 → 回填（评分/五维/因子/胜鞍）
│    is_task_finish() 状态机补齐
│
└─ 交互层：CLI（确认 gate：逐匹 y/N）→ Web 面板（M3，scheduler 队列已有）
```

数据流闭环见图 docs 上方示意图：情报+库存 → 种马规划 → 人工确认 → 自动育成 → **回填 my_studs.csv** → 下一次规划更准。

## 3. 任务清单

### M0 止血与环境落地（预估半天~1 天）

- [ ] **M0.1 git 收尾**
  - 新建 `.gitattributes`：`* text=auto eol=lf`；图片/二进制声明；随后 `git add --renormalize` 一次
  - `.gitignore` 追加：`my_inventory/`（隐私，防 add -A 上传）、`resource/umamusume/chara_icon/`、`resource/umamusume/support_card_img/`、`NVIDIA Corporation/`、`*.log`
  - 决策点①：chara_icon(275 图 19MB)+support_card_img(316 图 35MB)+2 个 manifest 是"图标入库"半成品——**建议图片不入库、tools 脚本入库**（fetch_game_images.py / fetch_support_cards.py / gen_inventory_template.py + manifest 生成逻辑），功能接 UI 后再议
  - 决策点②：当前 uncommitted（fuzzy_match/ocr_variant/kaisen_*/public assets）多为 stat 假阳性，提交前以 `git diff --stat` 复核真伪
- [ ] **M0.2 依赖重写**
  - 新增 `requirements.in`（分组注释）：删除 `opencv-python`（contrib 为超集）；显式 `numpy<2`、`paddleocr>=2.7,<3`、`paddlepaddle==2.6.2`、`setuptools<70` 保留
  - `pip-compile` 生成全量锁定的 `requirements.txt`（含传递依赖）
  - 实机验证：py3.11 venv 下清华源可装到 paddlepaddle==2.6.2 cp311 wheel（缺则换官方源/加备源）
- [ ] **M0.3 入口脚本**
  - `install.ps1` 重写：探测本机 python 3.10/3.11（优先 3.11）→ 建 venv → 安装锁版 requirements；源地址变量化（默认清华）
  - `run.ps1`：去掉 `check_update.py` 调用（其要求分支为 dev，与当前主干工作流不符）
  - `main.py:10-12` 版本校验放宽为 `3.10 <= v < 3.13`；`check_update.py` 标注废弃或改按 origin/main 检查
- [ ] **M0.4 P0 逻辑/安全修复**
  - `scenario_event.py:11-23`：`turn_operation == 枚举` → `turn_operation.turn_operation_type == 枚举`（注意 None 判空）
  - `cultivate.py:354`：越界容错 `>` → `>=`
  - `bot/server/handler.py`：兜底路由 resolve 后校验 `realpath` 位于 public 内（禁 `..`）；CORS 去掉 `allow_credentials=True` 或收敛 origin
  - `bot/conn/os.py:13` 去 `shell=True`（改用参数列表/shlex），随 `u2_ctrl.py` 调用面小改并实测 adb 命令
  - `context.py:65 is_task_finish()` 先做最小实现调研（需读懂 executor/scheduler 契约，原则：cultivate 正常完成路径置标志；做不动则标 TODO 移 M2，不硬塞）
- **M0 验收**：全新 py3.11 venv 一键安装成功 → `main.py` 起 8071 且首页可开 → `git status` 干净、无未决 P0 → 填好 `my_inventory/` 三表后 `python module/umamusume/asset/stud_planner.py --inventory-check` 通过

### M1 规划闭环（预估 1~2 天）—— 你最先能日常使用的一档

- [ ] **M1.1 建 `module/umamusume/planning/` 包**
  - `cup_info.py`：CupInfo 模型（race_name / venue / distance / surface / direction / weather / condition / style / 备注），`--race` 走 race_bwiki 查证 + 7 参数手填覆盖，读写 `my_inventory/cup_info.json`
  - `inventory.py`：InventoryService——三表校验（列/值域/重复）、缺填定位、`add_stud()` 追加接口（供 M2 回填）
  - `planner_api.py`：把 stud_planner 的打分/缺口/配卡/多代逻辑封装 `plan(cup, inventory, opts) -> Plan`（**只收敛不改算法**）；保留原 CLI 兼容
- [ ] **M1.2 stud_planner.py 拆分**（1522 行职责混杂，配合库化进行）
  - 拆：models / inventory 加载 / 打分 / 缺口 / 配卡 / report(md) / cli；行为零变化，跑 `docs/stud_planner_example.md` 样例回归
- [ ] **M1.3 新增统一 CLI 入口**（替代零散 `python module/...py`）
  - `python -m umamusume_plan plan --cup-file my_inventory/cup_info.json [--top 5]`
  - `python -m umamusume_plan cup --race 中山大奖赛`（写 cup_info.json）
  - 输出 `my_inventory/plan_<日期>.json` + 人类可读 md（复用现有 render_report）
- **M1 验收**：一条命令 = "把下次大赛发给项目 → 拿到针对该大赛、针对我账号的逐代养成计划"，报告里候选马娘均来自 my_characters、配卡只出现我拥有的卡

### M2 育成闭环（预估 2~3 天）

- [ ] **M2.1 target_build 接通**：`run()` 改为从 Plan 条目生成 BuildSpec（替代 BUILD_PRESETS demo）；TARGET_BUILD_ENABLED 在用户确认后试点置 True
- [ ] **M2.2 局末回填**：cultivate 完成路径后解析结局（评分/五维/抽到的因子/适性/胜鞍 G1）→ `InventoryService.add_stud()` 写回 my_studs.csv；`is_task_finish()` 同步完善
- [ ] **M2.3 胜鞍分实装**：affinity 合计 = 固定相性分（已有）+ 胜鞍分（读双方 my_studs.跑过的G1 交集；金章亦计）
- [ ] **M2.4 CLI 确认 gate**：`plan.json` 逐项打印 → 逐匹 y/N → 生成待执行队列；串行执行 cultivate，每局结束回填并续跑
- **M2 验收**：跑完 1 局 → my_studs.csv 新增该马记录 → 重跑 M1 plan 能看到新种马进候选/缺口收窄；育成中断可续
- **风险**：连续数小时无人值守育成 → 需局级失败重试与"识别异常即暂停"（M2.5 增补）

### M3 交互打磨（后置，不挡主路）

- [ ] Web 确认面板：大赛登记表单 + 计划逐匹确认 + 进度/日志（复用 bot scheduler 队列，新增 approve 任务型）
- [ ] 前端升级：删 electron、vite 3→5+、axios 视情移除；`public/` 构建产物流程自动化（build→copy 脚本）
- [ ] CI 最小门禁：python-build.yml 加 pytest 步骤；补 asset 纯逻辑测试（skill_order/affinity/race_schedule…）

## 4. 明确不做 / 待议

- OCR 换 RapidOCR / paddle 3.x：暂不做（环境问题已由 3.11+锁版解决）
- 大赛对手情报（BP/环境/参赛者）：属攻略层，等大赛赛制数据补充后再议
- 图标/卡图素材入库：默认不入库（54MB）；manifest 与抓取脚本可入库
- 凯旋门剧本实测数据、部分比赛名 resolver 缺口（有马记念 等）：沿用现状，遇缺即补

## 5. 风险清单

1. **paddlepaddle==2.6.2 在 py3.11+清华源**是否有 cp311 win wheel——M0.2 最先验证，缺则换官方源（已知 cp38–cp312 官方有）
2. **is_task_finish 语义**牵动 scheduler，M0.4 若调研不清就降级为 M2 与 target_build 一起改，避免半吊子改动
3. **并行会话操作同一仓库**（体检时曾观测到 HEAD 被推进）：改代码前先 `git pull`/确认 HEAD，提交前 `git diff --stat` 复核
4. 现有 tests 是独立脚本风格、pytest 收集不到——M3 前不强行迁移，改动 asset 逻辑时手动跑 `tools/regress_name_resolver.py` 与对应 test_*.py 回归

## 6. 执行顺序（依赖关系）

```
M0.2(paddle wheel 验证) ─┬─ M0.3(脚本) ─ M0.4(bug/安全) ─ M1 ─ M2 ─ M3
M0.1(git) 可随时并行/先行
```
建议提交节奏：M0 一个 commit（或按 git/依赖/bugfix 三个）、M1 每服务一个、M2 每闭环一个，均推送 origin/main。
