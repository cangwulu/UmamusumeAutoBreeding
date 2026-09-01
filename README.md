# UmamusumeAutoTrainer

> 国服 / 简体中文版《闪耀！优俊少女》（赛马娘）自动育成工具。
> 本仓库是 [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer) 的衍生品，在原有自动育成能力之上，新增了**数据资产层**与**目标构筑（种马）骨架**。

> 当前维护仓库：https://github.com/cangwulu/UmamusumeAutoBreeding

---

## 📌 关于本项目

- **上游原项目**：[shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer)，作者 [@shiokaze](https://github.com/shiokaze)
- **本仓库定位**：基于上游持续演进的独立项目，重点扩展**数据资产**（BWIKI 技能 / 事件 / 马娘数据、马娘自带技能查询）与**目标构筑（种马）**能力，作为可长期维护的项目存在。
- ⚠️ 目前仅支持**国服 / 简体中文版**，不支持其他版本（含国际服）。

---

## 🆕 本仓库新增与增强功能

| 模块 | 文件 | 说明 |
|------|------|------|
| **BWIKI 数据资产层** | `resource/umamusume/data/*.json` | 从 BWIKI 抓取的权威数据：技能速查表（1000 条，含评价分）、巅峰杯事件（161 个）、马娘形态（139 个，成长率 + 适应性）、马娘 → 自带技能归属库（130 角色） |
| **技能排序** | `module/umamusume/asset/skill_order.py` | 基于 BWIKI 评价分对候选技能排序，供育成主循环贪心选技 |
| **马娘自带技能查询** | `module/umamusume/asset/chara_skills.py` | 查询任意马娘的固有 / 觉醒 / 初始技能；`suggest_not_to_learn()` 可剔除已自带技能，避免白花技能点重复学习 |
| **事件库与匹配** | `module/umamusume/asset/event_db.py` | 事件数据结构与匹配逻辑（基于 BWIKI 事件表构建） |
| **目标构筑（种马）骨架** | `module/umamusume/script/cultivate_task/target_build.py` | **早期阶段**：按外部规划好的"规格"（技能 / 适应性 / 属性阈值）驱动育成的骨架，`BuildSpec` + `TargetBuildPlanner` 接口已就位，策略逻辑待填充 |

### 数据抓取脚本（`tools/`，不参与运行时）

仅用于重建 / 更新数据资产：

- `fetch_bwiki_skills.py` — 抓取 BWIKI 技能速查表（`#jn-json` 容器）
- `fetch_bwiki_extra.py` — 抓取事件 / 马娘 HTML 表格（`--no-chars` / `--no-events` 可跳过）
- `build_chara_skills.py` — 由 pretty-derby `db.json` + `zh_CN.json` 构建马娘 → 技能归属库
- `build_event_db.py` / `fetch_upstream.py` — 事件库构建 / 上游同步

---

## 📖 术语说明：本文的「种马」

本仓库提到的"养种马 / 种马"，指**你在外部育成模拟器 / 配种规划器上推理出的"每一代目标马娘规格"（技能 / 适应性 / 属性阈值）**，由程序按规格自动操纵模拟器练出来。

它**不是**游戏内的繁殖 / 因子继承机制。对应代码模块为 `target_build.py`（目标构筑），命名刻意不使用 `breeding` / `inherit`，以便日后留给真正的游戏内繁殖功能。

---

## 📁 项目结构（节选）

```
UmamusumeAutoTrainer/
├── main.py / run.ps1 / install.ps1      # 启动入口与安装脚本
├── config.yaml                         # 模拟器 / 育成配置
├── bot/                                # 底层：adb、OCR、图像识别、模糊匹配
├── module/umamusume/
│   ├── asset/                          # 数据资产层（本仓库重点）
│   │   ├── skill_order.py              # 技能排序（评价分）
│   │   ├── chara_skills.py             # 马娘自带技能查询
│   │   ├── event_db.py                 # 事件库与匹配
│   │   ├── point.py / template.py / ui.py
│   │   └── __init__.py                 # import cv2，测试时需注意
│   ├── scenario/                       # 各剧本（URA / 青春杯 / 凯旋门）
│   └── script/cultivate_task/          # 育成主循环
│       ├── cultivate.py                # 主循环（含 target_build 挂接点，默认关闭）
│       └── target_build.py             # 目标构筑骨架（早期）
├── resource/umamusume/data/            # 运行时 JSON 数据
├── tools/                             # 一次性构建 / 抓取脚本（不参与运行时）
└── docs/                              # 设计文档
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

- [x] **目标构筑（种马）决策逻辑草稿**：`target_build.py` 已实现首版「纯逻辑决策核心」（`choose_training` / `choose_skills_to_learn` / `spec_met` / `evaluate_aptitude` / `next_action`），并复用 `chara_skills.suggest_not_to_learn()` 跳过马娘自带技能；带 `simulate` 子命令可离线演示（无需模拟器）。
- [ ] **接入育成主循环**：把 `TargetBuildPlanner.run(ctx, spec)` 接到 `cultivate.py` 真实 ctx（读取属性/技能、操纵模拟器执行训练/学技能/休息），并按 `CultivateGoal.BUILD` 路由。
- [ ] 将 `chara_skills.suggest_not_to_learn()` 接入技能学习循环，避免重复学习自带技能
- [ ] 事件选项支持配置
- [ ] 自动完成每日金币 / 支援点 / JJC
- [ ] 凯旋门剧本完善与优化
- [ ] 育成中 AI 逻辑优化（含定时执行任务）

---

## 📜 许可证与版权声明

本项目是 [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer) 的**衍生作品（fork）**。

- **上游原项目**：作者 [@shiokaze](https://github.com/shiokaze)。上游**未指定开源许可证**，其原始代码的所有权利由原作者保留。
- **本仓库新增与修改的代码**：采用 [MIT License](LICENSE) 开源协议。
- **使用与再分发**：基于本仓库进行二次开发或再分发时，请保留本声明，就新增部分遵守 MIT 协议，并尊重上游原作者 @shiokaze 的贡献与权利。
- **数据来源**：[BWIKI（biligame 赛马娘 wiki）](https://wiki.biligame.com/umamusume)、[pretty-derby db](https://github.com/uma-meow/pretty-derby)。游戏内容版权归 Cygames / 哔哩哔哩所有。

---

## 🤝 参与开发

欢迎提交 Issue 与 Pull Request。

- 上游原作者：[@shiokaze](https://github.com/shiokaze)
- 当前维护仓库：[@cangwulu/UmamusumeAutoBreeding](https://github.com/cangwulu/UmamusumeAutoBreeding)

---

*本项目仅供学习研究使用，请勿用于商业用途。*
