# UmamusumeAutoTrainer

> 国服 / 简体中文版《闪耀！优俊少女》（赛马娘）自动育成工具。
> 本仓库是 [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer) 的衍生品，在原有自动育成能力之上，构建了完整的**数据资产层**（技能 / 比赛 / 角色 / 事件 / 相性 / 评分）、**攻略知识层**（游戏机制 / 种马育成 / 凯旋门剧本 / 技能分级）与**目标构筑（种马）骨架**。

> 当前维护仓库：https://github.com/cangwulu/UmamusumeAutoBreeding

---

## 📌 关于本项目

- **上游原项目**：[shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer)，作者 [@shiokaze](https://github.com/shiokaze)
- **本仓库定位**：基于上游持续演进的独立项目，重点扩展**数据资产层**（BWIKI 技能 / 比赛 / 角色 / 事件 / 相性 / 评分）、**攻略知识层**（游戏机制 / 种马育成 / 凯旋门剧本 / 技能分级 / 支援卡事件）与**目标构筑（种马）**能力，作为可长期维护的项目存在。
- ⚠️ 目前仅支持**国服 / 简体中文版**，不支持其他版本（含国际服）。

---

## 🆕 本仓库新增与增强功能

### 数据资产层（`module/umamusume/asset/` + `resource/umamusume/data/`）

| 模块 | 文件 | 说明 |
|------|------|------|
| **技能排序** | `skill_order.py` | 基于 BWIKI 评价分对候选技能排序，供育成主循环贪心选技 |
| **马娘自带技能** | `chara_skills.py` | 查询固有 / 觉醒 / 初始技能；`suggest_not_to_learn()` 剔除已自带技能 |
| **相性查询** | `affinity.py` | `pair_score` / `triple_score` / `inherit_scores` / `best_partners`，84 角色 / 792 关系组 |
| **评分计算** | `rating.py` | 五维分段线性 + 技能评价分 × 适性倍率 + 评级表 G~UB；1200+ 高斜率系数 |
| **比赛查询** | `race_bwiki.py` | `resolve` 任意别名→简中权威名；313 场含 lane 内 / 外圈 |
| **三年赛程** | `race_schedule.py` | `ScheduleDB.at(year,month,half)` / `available(fan=)` 粉丝门槛筛选；316 条赛程 |
| **历战路线** | `route_planner.py` | 时间槽贪心，等级权重 × 适性契合，G1 永不跳 |
| **角色目标** | `chara_targets.py` | 81 角色 / 744 育成目标（含时间 / 粉丝门槛 / 比赛描述） |
| **角色事件** | `chara_events.py` | 81 角色 / 2213 有分支事件（含选项 + 效果中文） |
| **支援卡事件** | `support_events.py` | 283 卡 / 757 事件（源自 urarawin，角色名中日文均可搜） |
| **事件库** | `event_db.py` | 事件数据结构与匹配逻辑 |

### 攻略知识层（查询模块 + 结构化 JSON）

| 模块 | 文件 | 说明 |
|------|------|------|
| **游戏机制** | `game_mechanics.py` | 心情倍率 / 训练副属性 / 距离分类 / 巅峰杯商店 36 种道具 / 因子继承规则 / 三剧本机制 / 相性避坑 |
| **种马育成** | `breeding_guide.py` | 5 步流水线 / 因子优先级 / 技能 T1-T2 / 金章比赛 / 2025 现代实践 |
| **凯旋门剧本** | `larc_guide.py` | 群星槽 / SS 对决 / 魔咒 / 远征 / 配卡 / 属性目标 / 时间线 |
| **技能分级** | `skill_tierlist.py` | 7 大类 S-F 分级 + 距离 × 跑法矩阵 + 选择原则 |

### 目标构筑（种马）

| 模块 | 文件 | 说明 |
|------|------|------|
| **目标构筑** | `target_build.py` | `BuildSpec` + `TargetBuildPlanner` 决策核心，已以"默认关闭的 per-turn 钩子"接入 `cultivate.py` 主循环 |

### 数据抓取脚本（`tools/`，不参与运行时）

仅用于重建 / 更新数据资产：

- `fetch_bwiki_skills.py` — 抓取 BWIKI 技能速查表（`#jn-json` 容器）
- `fetch_bwiki_extra.py` — 抓取事件 / 马娘 HTML 表格
- `build_chara_skills.py` — 由 pretty-derby `db.json` 构建马娘 → 技能归属库
- `build_affinity.py` — 抓取 BWIKI 相性计算器 → `affinity.json`
- `build_rating_data.py` — 抓取 BWIKI 评分计算器 → `rating.py` + `skill_upgrade.json`
- `build_race_data.py` — 抓取 BWIKI 比赛 + 简中比赛页 → `race_bwiki.json` + 比赛横幅图
- `build_race_schedule.py` — 解析 NGA 三年赛程 → `race_schedule.json` + 交叉比对 + `--patch` 增强
- `build_chara_targets.py` — 抓取 BWIKI 角色子页 → `chara_targets.json`
- `build_chara_events.py` — SMW 查询角色事件子页 → `chara_events.json`
- `build_guide.py` — 抓取大赛攻略页 → 图文整合 HTML
- `integrate_urarawin.py` — urarawin 数据库集成 → `support_events.json`

---

## 📖 术语说明：本文的「种马」

本仓库提到的"养种马 / 种马"，指**游戏内已经育成结束、可被后代继承因子的马娘**（每次育成可选 2 位种马）。这是游戏内真实的因子继承机制：蓝（属性）/ 粉（适性改造）/ 绿（继承固有）/ 白（比赛 / 技能 / 剧本因子）四种因子，继承 3 次（初始 / 第二年 4 月 / 第三年 4 月），后两次概率继承且看相性。

对应代码模块为 `target_build.py`（目标构筑），命名保留 `target_build` 避免与未来真正的配种继承 `breeding` 冲突。完整机制见 `docs/strategy_integrated.md`。

---

## 📁 项目结构（节选）

```
UmamusumeAutoTrainer/
├── main.py / run.ps1 / install.ps1      # 启动入口与安装脚本
├── config.yaml                         # 模拟器 / 育成配置
├── bot/                                # 底层：adb、OCR、图像识别、模糊匹配
├── module/umamusume/
│   ├── asset/                          # 数据资产层 + 攻略知识层
│   │   ├── skill_order.py              # 技能排序（评价分）
│   │   ├── chara_skills.py             # 马娘自带技能查询
│   │   ├── affinity.py                 # 相性查询（固定相性分）
│   │   ├── rating.py                   # 评分计算（五维+技能+评级）
│   │   ├── race_bwiki.py               # 比赛查询（简中权威译名）
│   │   ├── race_schedule.py            # 三年完整赛程查询
│   │   ├── route_planner.py            # 历战路线生成器
│   │   ├── chara_targets.py            # 角色育成目标查询
│   │   ├── chara_events.py             # 角色自带事件查询
│   │   ├── support_events.py           # 支援卡事件查询（urarawin）
│   │   ├── game_mechanics.py           # 游戏核心机制查询
│   │   ├── breeding_guide.py           # 种马育成方法论查询
│   │   ├── larc_guide.py               # 凯旋门剧本攻略查询
│   │   ├── skill_tierlist.py           # 技能推荐分级查询
│   │   ├── event_db.py / point.py / template.py / ui.py
│   │   └── __init__.py                 # import cv2，测试时需注意
│   ├── scenario/                       # 各剧本（URA / 青春杯 / 凯旋门）
│   └── script/cultivate_task/          # 育成主循环
│       ├── cultivate.py                # 主循环（含 target_build 挂接点，默认关闭）
│       └── target_build.py             # 目标构筑（可按规格练马，默认关闭）
├── resource/umamusume/data/            # 运行时 JSON 数据（20 个文件）
│   ├── skill_bwiki.json                # 1000 技能（含评价分）
│   ├── race_bwiki.json                 # 313 场比赛（含 lane 内/外圈）
│   ├── race_schedule.json              # 316 条三年赛程
│   ├── affinity.json                   # 84 角色 / 792 关系组
│   ├── chara_events.json               # 81 角色 / 2213 事件
│   ├── support_events.json             # 283 卡 / 757 事件
│   ├── game_mechanics.json             # 心情/训练/商店/因子/剧本
│   ├── breeding_guide.json             # 种马育成 5 步流水线
│   ├── larc_guide.json                 # 凯旋门剧本完整攻略
│   ├── skill_tierlist.json             # 7 大类 S-F 技能分级
│   └── ...                             # 其余数据文件
├── tools/                             # 一次性构建 / 抓取脚本（不参与运行时）
└── docs/                              # 设计文档 + 攻略
    ├── strategy_integrated.md          # 整合策略（比赛×凯旋门×种马）
    ├── guide_game_mechanics.md         # 游戏机制完全攻略
    ├── guide_tournament.html           # 大赛攻略图文整合
    └── race_gallery.html               # 313 场比赛图文图鉴
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

### 3. 配置

修改 `config.yaml`：

```yaml
bot:
  auto:
    adb:
      device_name: "127.0.0.1:16384" # 改为模拟器的 adb 端口
      delay: 0
    cpu_alloc: 4 # 分配的 cpu 数量
```

常见模拟器端口：
- （推荐）**mumu12**：`127.0.0.1:16384`
- **雷电 / 蓝叠**：`emulator-5554`

### 4. 模拟器设置

- 分辨率 **720 × 1280**，DPI **180**（竖屏）
- mumu 模拟器**不能开启后台保活**

### 5. 启动

双击 `run.ps1`。控制台出现 `UAT running on http://127.0.0.1:8071` 即启动成功，浏览器访问该地址通过 Web UI 配置任务并启动。

---

## ⚠️ 注意事项

1. 游戏内画面选项必须是**标准版**，不能是简易版
2. 含自选赛事 / 粉丝数要求的育成（如小栗帽第三年 G1、乌拉拉粉丝目标），需用对应马娘预设或自定义赛程
3. 目标属性尽量与支援卡类型比例匹配
4. 暂不支持选择育成马娘和种马，启动时使用游戏内上次记录；无记录需先手动选择
5. 不推荐携带友人卡（暂无友人卡专属策略）
6. 启动脚本时处于主菜单或任意育成界面

异常排查与常见问题见[上游原仓库说明](https://github.com/shiokaze/UmamusumeAutoTrainer)对应章节。

---

## 🗺️ 路线图 / TODO

### 已完成

- [x] **数据资产层**：技能排序 / 马娘自带技能 / 相性 / 评分 / 比赛 / 三年赛程 / 历战路线 / 角色目标 / 角色事件 / 支援卡事件
- [x] **攻略知识层**：游戏机制 / 种马育成方法论 / 凯旋门剧本攻略 / 技能推荐分级
- [x] **目标构筑决策逻辑草稿**：`target_build.py` 实现 `choose_training` / `choose_skills_to_learn` / `spec_met` / `next_action`，复用 `chara_skills.suggest_not_to_learn()` 跳过自带技能
- [x] **接入育成主循环（默认关闭）**：`cultivate.py` 新增 per-turn 钩子，异常自动回退原 RACE 流程
- [x] **比赛数据增强**：115 场 lane 内 / 外圈补全（从 NGA 赛程数据交叉比对）

### 待完成

- [ ] 将 `chara_skills.suggest_not_to_learn()` 接入技能学习循环，避免重复学习自带技能
- [ ] 将 `skill_tierlist` 分级引入 `cultivate.py` 技能学习贪心逻辑做优先级参考
- [ ] 事件选项支持配置
- [ ] 自动完成每日金币 / 支援点 / JJC
- [ ] 凯旋门剧本完善与优化（`larc_guide` 机制已结构化，待接入 `kaisen_scenario.py`）
- [ ] 育成中 AI 逻辑优化（含定时执行任务）

---

## 📜 许可证与版权声明

本项目是 [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer) 的**衍生作品（fork）**。

- **上游原项目**：作者 [@shiokaze](https://github.com/shiokaze)。上游**未指定开源许可证**，其原始代码的所有权利由原作者保留。
- **本仓库新增与修改的代码**：采用 [MIT License](LICENSE) 开源协议。
- **使用与再分发**：基于本仓库进行二次开发或再分发时，请保留本声明，就新增部分遵守 MIT 协议，并尊重上游原作者 @shiokaze 的贡献与权利。
- **数据来源**：[BWIKI（biligame 赛马娘 wiki）](https://wiki.biligame.com/umamusume)、[pretty-derby db](https://github.com/uma-meow/pretty-derby)、[urarawin.com](https://urarawin.com)、[NGA 玩家社区](https://bbs.nga.cn)。游戏内容版权归 Cygames / 哔哩哔哩所有。

---

## 🤝 参与开发

欢迎提交 Issue 与 Pull Request。

- 上游原作者：[@shiokaze](https://github.com/shiokaze)
- 当前维护仓库：[@cangwulu/UmamusumeAutoBreeding](https://github.com/cangwulu/UmamusumeAutoBreeding)

---

*本项目仅供学习研究使用，请勿用于商业用途。*
