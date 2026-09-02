# UmamusumeAutoTrainer

> 国服 / 简体中文版《闪耀！优俊少女》（赛马娘）自动育成 + 数据规划工具。
> 本仓库是 [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer) 的衍生品。在原有「画面识别 + 自动训练/比赛/休息/学技能」能力之上，构建了完整的**数据资产层**（技能 / 比赛 / 角色 / 事件 / 相性 / 评分）、**攻略知识层**（游戏机制 / 种马育成 / 凯旋门剧本 / 技能分级）、**名称统一解析层**、**种马缺口规划器**与 **Web 点选 / 规划界面**。

> 当前维护仓库：https://github.com/cangwulu/UmamusumeAutoBreeding

---

## 📌 定位

- **上游原项目**：[shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer)，作者 [@shiokaze](https://github.com/shiokaze)
- **两条能力线**：
  1. **自动育成**（继承上游）：OCR + 模板匹配识别画面，自动训练 / 比赛 / 休息 / 学技能 / 处理事件；
  2. **数据与规划**（本仓库重点）：把国服权威数据（BWIKI）+ 上游拆包数据（pretty-derby）+ 民间数据库（urarawin）结构化沉淀，提供查表 API 与**从大赛倒推种马缺口**的规划器。
- ⚠️ 仅支持**国服 / 简体中文版**，不支持国际服等其他版本。

---

## ✨ 核心能力一览

### 1. 自动育成（`module/umamusume/script/cultivate_task/`）

| 能力 | 说明 |
|------|------|
| **主循环** | 画面识别驱动：训练 / 休息 / 比赛 / 学技能 / 事件 / 剧本分支全自动 |
| **学技能** | 技能点超阈值自动进技能页；数据驱动排序（`skill_order` 综合分在同级桶内细分）；**剔除减益技能**（负分红技）与**马娘自带技能**（`suggest_not_to_learn`，P7） |
| **事件识别** | 马娘个人 / 协助卡 / 剧本三类事件画面统一路由 → OCR 事件名 → **事件库智能选层**（P2）：硬编码规则 → event_db(5330 条) 命中按上下文打分 → 默认选项 1 |
| **优选策略** | `event/strategy.py` 是事件选层的唯一策略入口，调养马策略只改这一个文件（P3） |
| **剧本** | URA / 青春杯 / 凯旋门三类剧本场景脚本 |
| **目标构筑（实验）** | `target_build.py` 按 `BuildSpec` 规格决策，已以默认关闭的 per-turn 钩子接入主循环 |

### 2. 数据资产层（`module/umamusume/asset/` + `resource/umamusume/data/`）

| 模块 | 数据规模 | 说明 |
|------|---------|------|
| `skill_order.py` + `skill_bwiki.json` | **1000 技能** | BWIKI 评价分排序；OCR 名模糊匹配（简中主库 + derby 兜底） |
| `chara_skills.py` + `chara_skills.json` | 130 角色 | 固有 / 觉醒 / 初始技能归属（pretty-derby 源）；`suggest_not_to_learn` 剔自带 |
| `skill_tierlist.py` | 7 大类 S-F | 技能分级 + 距离×跑法矩阵 |
| `affinity.py` + `affinity.json` | **95 角色 / 1259 关系组** | 官方拆包相性数据（master.mdb）；对拍 uma-tools 完全一致 |
| `saddle.py` | — | 胜鞍分（2023-02-24 现行规则：仅 G1 重合 +3pt/场，父辈间计入） |
| `race_bwiki.py` + `race_bwiki.json` | **313 场** | 任意别名 → 简中权威名；含 lane 内 / 外圈 |
| `race_schedule.py` | 316 条 | 三年赛程 `ScheduleDB.at(year,month,half)` |
| `route_planner.py` | — | 历战路线生成（时间槽贪心，G1 永不跳） |
| `chara_targets.py` | 81 角色 / 744 目标 | 育成目标比赛表 |
| `event_db.py` + `event_db.json` | **5330 事件** | 双路检索（事件名 + 末选项指纹）；`support` 协助卡 538 条含 urarawin 补全 |
| `chara_events.py` | 81 角色 / 2213 事件 | BWIKI 角色事件（含选项 + 中文效果） |
| `support_events.py` | 283 卡 / 757 事件 | 协助卡事件（urarawin 源，按卡组织） |
| `rating.py` | 五维+技能+评级 | 最终评分全公式 |
| `game_mechanics.py` / `breeding_guide.py` / `larc_guide.py` | JSON 结构化 | 机制 / 种马方法论 / 凯旋门攻略 |

### 3. 名称统一解析层（`module/umamusume/name_resolver.py`）

> 任何「表面名」（国服简中 / BWIKI 中文 / 台服 / 日文 / pretty-derby 译名）→ 日文规范键，是**全项目名字匹配的唯一入口**。

- `name_index.json`：**5483 规范键 / 约 1.2 万别名**，覆盖 马娘(152)/形态(204)/协助卡(316)/技能(819)/事件(3679)/比赛(313) 六类
- 角色事件简中名桥接：命中率 55% → **97%**（P4）
- 词面跨类冲突（如「一往无前」既是角色称号又是技能名）用 `canonical(prefer=...)` 按目标类型解析（P5）
- 详见 `docs/NAME_RESOLVER_OVERVIEW.md`

### 4. 种马缺口规划器（`stud_planner.py` + Web 界面）

> 从「下次大赛」倒推「我还差多远」→ 因子需求(蓝/粉/白/绿) → 多代养成计划 → 借位建议。

- **CLI**：`python module/umamusume/asset/stud_planner.py --race 中山大奖赛`
- **Web 点选页**：`public/planning.html` + `module/umamusume/planning/web_api.py` —— 浏览器点选拥有的马娘 / 协助卡（写回 `my_inventory/*.csv`）、登记大赛、运行规划
- **红因子继承概率**（P2）：抄自 uma-tools 的 1★1%/2★3%/3★5% ×(1+相性/100) 模型，报告给出「A→S 概率段需几颗 1★红因子 / 期望育成次数」
- 相性数据官方化 + 胜鞍按现行规则（P0/P1）
- 输入是你在 `my_inventory/` 填的库存（模板由 `tools/gen_inventory_template.py` 生成）

### 5. 数据抓取 / 更新脚本（`tools/`，不参与运行时）

**国服更新后一键刷新**：`python tools/update_assets.py`（马娘线 / 协助卡线 / 全量 / dry-run / 自动备份，详见脚本头部）。

| 脚本 | 抓取 / 构建 |
|------|------------|
| `fetch_bwiki_extra.py` | BWIKI 马娘一览（成长率 / 适性）与通用事件 |
| `fetch_support_cards.py` | BWIKI 简中协助卡图鉴（316 卡） |
| `fetch_bwiki_skills.py` | BWIKI 技能速查表（`#jn-json` 容器） |
| `fetch_upstream.py` | pretty-derby `db.json` + `zh_CN.json`（增量 + 镜像回退） |
| `build_chara_skills.py` + `enrich_chara_skills_jp.py` | 上游 → 马娘技能归属（按名对齐形态） |
| `build_event_db.py` | 上游 → 中文事件库（全量重建） |
| `build_chara_targets.py` / `build_chara_events.py` | BWIKI SMW → 育成目标 / 角色事件 |
| `integrate_urarawin.py` + `merge_urarawin_support_events.py` | urarawin 协助卡事件 → 补进事件库 |
| `build_affinity_from_mdb.py` | 官方 master.mdb → 相性数据 |
| `build_name_index.py` | 全部译名 → 统一名称索引（产物 `name_index.json`） |
| `build_race_data.py` / `build_race_schedule.py` / `build_rating_data.py` 等 | 比赛 / 赛程 / 评分数据 |

⚠️ 数据产物 JSON 一律**提交进仓库**，运行时不联网；只有更新才需要联网抓取。

---

## 📖 术语：本文的「种马」

本仓库的「养种马 / 种马」指**游戏内已育成结束、可被后代继承因子的马娘**（每次育成可选 2 位），非外部规格。因子分四种：蓝（属性）/ 粉（适性改造，初始继承封顶 A）/ 绿（继承固有）/ 白（比赛 / 技能 / 剧本因子）；继承 3 次（初始 / 第 2 年 4 月 / 第 3 年 4 月），后两次概率触发且看相性。

> 规划口径：属性缺口主要靠配卡训练补（9 蓝理想配置单属性最多 +63）；A→S 只能靠概率性继承；固定相性分普遍偏低、真正拉开差距的是**胜鞍分**（G1 重合，历战是主引擎）。
> 完整机制见 `docs/strategy_integrated.md`。

---

## 📁 项目结构（节选）

```
UmamusumeAutoTrainer/
├── main.py / run.ps1 / install.ps1    # 启动入口与安装脚本
├── config.yaml                        # 模拟器 / 育成配置
├── bot/                               # 底层：adb、OCR、图像识别、模糊匹配
├── module/umamusume/
│   ├── name_resolver.py               # 统一名称解析层（无 cv2 依赖）
│   ├── asset/                         # 数据资产层 + 攻略知识层（stud_planner 等）
│   ├── scenario/                      # 剧本（URA / 青春杯 / 凯旋门）
│   ├── script/cultivate_task/         # 育成主循环
│   │   ├── cultivate.py               # 主循环（技能/事件/剧本分支）
│   │   ├── ai.py / parse.py           # 决策与画面解析
│   │   ├── event/                     # 事件模块（P2/P3）
│   │   │   ├── manifest.py            # 编排：硬编码 → 查库 → 问策略 → 兜底
│   │   │   ├── strategy.py            # ★ 优选策略唯一入口（调策略只改这里）
│   │   │   ├── event_choice.py        # 效果解析 + 上下文打分（纯工具）
│   │   │   └── scenario_event.py      # 硬编码事件规则（新年/青春杯队名）
│   │   └── target_build.py            # 目标构筑（实验，默认关闭）
│   └── planning/                      # 规划 API + CLI（cup/inventory/web_api）
├── resource/umamusume/data/           # 运行时 JSON（全部入库，运行时不联网）
├── my_inventory/                      # ★ 你的库存填报 CSV（stud_planner 输入）
├── tools/                             # 抓取 / 构建 / 更新脚本（不参与运行时）
│   └── update_assets.py               # 国服更新一键刷新入口
├── tests/                             # 回归测试（含 uat 集成冒烟）
└── docs/                              # 设计文档 + 攻略
    ├── strategy_integrated.md         # 整合策略（比赛×凯旋门×种马/因子）
    ├── NAME_RESOLVER_OVERVIEW.md      # 名称解析层设计
    ├── research_umalator_succession_planner.md  # uma-tools/巴哈调研（P0-P3 来源）
    └── ...
```

---

## ⚡ 使用说明

### 1. 下载

```bash
git clone https://github.com/cangwulu/UmamusumeAutoBreeding.git
cd UmamusumeAutoTrainer
```

### 2. 安装依赖

1. 安装 **Python 3.10.9**（[下载地址](https://www.python.org/downloads/release/python-3109/)）
2. 双击运行 `install.ps1`（若用记事本打开，请右键 → 打开方式 → PowerShell 运行；运行时当前目录不能有 `venv` 文件夹）
   - 非中国大陆 / 不需要国内镜像时，可将 `install.ps1` 中 pip 命令改为 `pip install --upgrade -r requirements.txt`

### 3. 配置 `config.yaml`

```yaml
bot:
  auto:
    adb:
      device_name: "127.0.0.1:16384" # 改为模拟器的 adb 端口
      delay: 0
    cpu_alloc: 4 # 分配的 cpu 数量
```

常见模拟器端口：**mumu12** `127.0.0.1:16384`（推荐）；**雷电 / 蓝叠** `emulator-5554`

### 4. 模拟器设置

- 分辨率 **720 × 1280**，DPI **180**（竖屏）；mumu 模拟器**不能开启后台保活**

### 5. 启动

双击 `run.ps1`。控制台出现 `UAT running on http://127.0.0.1:8071` 即启动成功，浏览器访问：

- `/` —— 自动育成任务 Web UI（配置马娘 / 协助卡 / 技能 / 剧本后启动）
- `/planning.html` —— 库存点选 + 大赛登记 + 种马规划（读 `my_inventory/`）

> 数据 / 规划工具也可以脱离模拟器单独用：`python module/umamusume/asset/stud_planner.py --race 中山大奖赛` 等 CLI 见各模块 docstring。

---

## 🧪 回归测试

```bash
python tests/test_event_choice.py          # 事件打分(managed py)
python tests/test_event_choice_db.py       # 事件库端到端(真实 5330 条)
python tests/test_event_strategy.py        # 优选策略入口
python tests/test_name_index_alias.py      # 名称索引/别名(P4/P5)
python tests/test_skill_order.py           # 技能库匹配/排序(P6)
python tests/test_stud_pink_factor.py      # 红因子概率模型(P2)
python tests/test_owned_skill_filter.py    # 学技能剔除自带(P7, 需 uat 环境)
python tools/regress_name_resolver.py      # 名称解析回归
```

---

## ⚠️ 注意事项

1. 游戏内画面选项必须是**标准版**，不能是简易版
2. 含自选赛事 / 粉丝数要求的育成（如小栗帽第三年 G1、乌拉拉粉丝目标），需用对应马娘预设或自定义赛程
3. 目标属性尽量与协助卡类型比例匹配（`expect_attribute` 与配卡联动）
4. 自动育成暂不支持自动选马娘 / 种马，启动时使用游戏内上次记录；无记录需先手动选择
5. 学技能「剔除马娘自带」需在任务配置里填**当前育成马娘**（attachment `cultivate_chara`），可选
6. 启动脚本时处于主菜单或任意育成界面

异常排查与常见问题见[上游原仓库说明](https://github.com/shiokaze/UmamusumeAutoTrainer)对应章节。

---

## 🗺️ 路线图

### ✅ 已完成

- **数据资产层**：技能排序 / 马娘自带技能 / 官方相性(2133组) / 胜鞍现行规则 / 评分 / 比赛 / 三年赛程 / 历战路线 / 角色目标 / 角色事件 / 协助卡事件(urarawin 并入 event_db)
- **名称统一解析层**：5483 键 / 6 类覆盖 / 事件简中名桥接(P4) / 跨类冲突 prefer 解析(P5)
- **事件识别接入主循环**（P2）：马娘/协助卡/剧本事件统一走事件库智能选层
- **优选策略模块**（P3）：`event/strategy.py` 唯一入口
- **红因子继承概率模型**（P2 规划线）：uma-tools 模型抄入 stud_planner，报告含概率表
- **种马缺口规划器**：CLI + Web 点选/规划页 + 多代养成计划 + 行动清单(借位/升级)
- **目标构筑决策逻辑**：`target_build.py` + 主循环钩子（默认关闭，异常自动回退）
- **国服更新一键刷新**：`tools/update_assets.py`
- **回归测试**：11 个测试文件 + name_resolver 回归

### 🔜 待推进

- [ ] 事件选择接入真实育成验证（需要跑一轮完整育成观察命中率与打分质量）
- [ ] `skill_tierlist` 分级进一步参与技能贪心优先级
- [ ] 育成 AI 逻辑优化（含定时执行 / 自动完成每日金币 / 支援点 / JJC）
- [ ] 凯旋门剧本完善（`larc_guide` 已结构化，待与 `kaisen_scenario.py` 深度联动）
- [ ] 借马推荐 6 槽亲代建模 + 相性逐项明细展示
- [ ] Web 界面补「当前育成马娘」输入以启用 P7 自带技能剔除

---

## 📜 许可证与版权声明

本项目是 [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer) 的**衍生作品（fork）**。

- **上游原项目**：作者 [@shiokaze](https://github.com/shiokaze)。上游**未指定开源许可证**，其原始代码的所有权利由原作者保留。
- **本仓库新增与修改的代码**：采用 [MIT License](LICENSE) 开源协议。
- **使用与再分发**：基于本仓库二次开发或再分发时，请保留本声明，就新增部分遵守 MIT 协议，并尊重上游原作者 @shiokaze 的贡献与权利。
- **数据来源**：[BWIKI](https://wiki.biligame.com/umamusume)、[pretty-derby db](https://github.com/uma-meow/pretty-derby)、[urarawin.com](https://urarawin.com)、[NGA 玩家社区](https://bbs.nga.cn)、[巴哈姆特攻略](https://forum.gamer.com.tw/)。游戏内容版权归 Cygames / 哔哩哔哩所有。

---

## 🤝 参与开发

欢迎提交 Issue 与 Pull Request。

- 上游原作者：[@shiokaze](https://github.com/shiokaze)
- 当前维护仓库：[@cangwulu/UmamusumeAutoBreeding](https://github.com/cangwulu/UmamusumeAutoBreeding)

---

*本项目仅供学习研究使用，请勿用于商业用途。*
