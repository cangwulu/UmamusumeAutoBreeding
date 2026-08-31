# 凯旋杯(プロジェクトL'Arc)剧本支持评估报告

> 评估对象:本仓库(UAT, UmamusumeAutoTrainer, 国服客户端 com.bilibili.umamusu)
> 评估日期:2026-08-31
> 结论先行:完全可行,但**核心瓶颈不是写代码,而是游戏截图素材**。素材齐全后,AI 辅助下编码约 1~2 周(业余时间)。

---

## 1. 现有架构:一个剧本是怎么"接"进这个项目的

引擎主循环(`bot/engine/executor.py`):

```
截图 → 模板匹配识别当前界面(UI) → 按 UI 分发脚本(manifest.py 的 script_dicts) → 执行 → 0.5s 后循环
```

一个剧本涉及的全部代码位置:

| 层 | 文件 | 职责 | 剧本相关? |
|---|---|---|---|
| 剧本类 | `module/umamusume/scenario/base_scenario.py` | 抽象基类,5 个方法 | 是,每个剧本一个子类 |
| 剧本类 | `scenario/ura_scenario.py` / `aoharuhai_scenario.py` | 日期/距比赛日裁剪区域、训练属性增量解析、支援卡解析(全部是**像素坐标+OCR**) | 是 |
| 注册 | `module/umamusume/define.py` | `ScenarioType` 枚举 | 是,加一个值 |
| 注册 | `module/umamusume/context.py` | match 语句创建剧本实例 | 是,加一个分支 |
| 主流程 | `script/cultivate_task/cultivate.py`(616 行) | 每个 UI 对应的脚本函数:进剧本、训练、比赛、技能、结算 | 部分(青春杯比赛流程内嵌) |
| 决策 | `script/cultivate_task/ai.py`(287 行) | 每回合选哪个训练(属性/支援卡/等级加权打分) | 少量(URA 事件权重特例) |
| 解析 | `script/cultivate_task/parse.py`(471 行) | 日期、体力、五维、训练加成、事件解析 | 部分(日期/训练调用剧本类) |
| 资产 | `asset/template.py` | 模板注册,指向 `resource/umamusume/{ui,ref,btn,scenario}/` 的 png | 是,新界面=新模板 |
| 资产 | `asset/ui.py` | UI 定义(模板组合) | 是 |
| 资产 | `asset/point.py` | 点击坐标 | 部分 |
| 资产 | `asset/race_data.py` + `resource/umamusume/race/` | 比赛识别数据 | 部分 |
| 事件 | `script/cultivate_task/event/manifest.py` | 事件名→选项映射(攻略知识) | 是 |
| 配置 | `module/umamusume/task.py` | TaskDetail 字段 | 是,新配置加字段 |
| 配置 | `scenario/configs.py` | 剧本专属配置类(UraConfig/AoharuConfig) | 是 |
| 前端 | `web/src/components/TaskEditModal.vue` | 任务表单(剧本下拉、剧本配置) | 是 |
| 前端 | `web/src/components/umamusume/UmamusumeTaskDetailInfo.vue` | 剧本名显示(注释写着 Add more scenarios here) | 是,加一个分支 |

关键认识:**剧本类只负责"界面裁剪+解析",主流程和决策是共享的**。所以凯旋杯支持 = 新剧本类 + 新界面模板/坐标 + 凯旋杯特有流程脚本,不需要重写引擎。

---

## 2. 凯旋杯改造点清单(按难度分三档)

### A 档:纯机械改动(不需要截图,AI 可独立完成,约 0.5 天)

| # | 文件 | 改动 |
|---|---|---|
| 1 | `module/umamusume/define.py` | `ScenarioType` 增加 `SCENARIO_TYPE_KAISEN = 3` |
| 2 | `module/umamusume/scenario/kaisen_scenario.py` | 新建,继承 `BaseScenario`(5 个方法先按 URA 抄,坐标后面调) |
| 3 | `module/umamusume/context.py` | match 增加凯旋杯分支 |
| 4 | `module/umamusume/scenario/configs.py` | `KaisenConfig`(先留空结构,后续按需求填) |
| 5 | `module/umamusume/task.py` | TaskDetail/build_task 加凯旋杯配置字段 |
| 6 | `web/src/components/TaskEditModal.vue` | 剧本下拉加"凯旋杯"选项 + 配置表单 |
| 7 | `web/src/components/umamusume/UmamusumeTaskDetailInfo.vue` | scenarioName 加 scenario===3 分支 |

### B 档:需要截图素材的改动(素材到位后 AI 可做,约 1~2 天)

| # | 文件 | 改动 |
|---|---|---|
| 8 | `asset/template.py` | 注册凯旋杯模板:`UI_SCENARIO_KAISEN` + 新界面模板 |
| 9 | `resource/umamusume/scenario/scenario_kaisen.png` | 剧本选择页的凯旋杯卡片截图(裁剪) |
| 10 | `resource/umamusume/ui/` | 凯旋杯各界面模板图(参照 ui/ 现有 73 张的命名和裁剪方式) |
| 11 | `resource/umamusume/ref/` | 新参考图(远征按钮、特殊标记等) |
| 12 | `asset/ui.py` | UI 定义:模板 + 匹配区域 |
| 13 | `asset/point.py` | 新界面点击坐标 |
| 14 | `asset/race_data.py` + `resource/umamusume/race/` | 凯旋门赏相关比赛数据 |
| 15 | `scenario/kaisen_scenario.py` | 根据截图确定 5 个方法的真实像素坐标 |

### C 档:需要理解凯旋杯机制 + 反复联调(3~7 天)

| # | 文件 | 改动 |
|---|---|---|
| 16 | `cultivate.py` | 凯旋杯特有流程脚本(远征流程、凯旋门赏特化界面)+ `manifest.py` script_dicts 注册 |
| 17 | `parse.py` | 新界面的解析函数(若布局与 URA 差异大) |
| 18 | `ai.py` | 凯旋杯决策维度(远征优先级、シナリオリンク等,可选) |
| 19 | `event/manifest.py` | 凯旋杯独有事件的选项映射(**需要攻略知识,AI 不知道**——要么社区攻略,要么默认选 1 先跑起来) |

---

## 3. 你需要提供的截图素材清单(核心瓶颈!)

> 要求:模拟器固定分辨率(项目按 720x1280 竖屏坐标写的,截图分辨率必须一致)、国服客户端、每项 2~3 张不同状态、PNG 原图、不要缩放/滤镜。

| # | 界面 | 用途 | 优先级 |
|---|---|---|---|
| 1 | 育成页-剧本选择(含凯旋杯卡片) | 剧本卡片模板 `scenario_kaisen.png` | ★★★ |
| 2 | 育成准备-最终确认页 | 确认通用流程是否适用 | ★★ |
| 3 | 凯旋杯训练主界面(日期/体力/五维/支援卡/按钮全貌) | 主菜单解析、日期裁剪区域 | ★★★ |
| 4 | 训练选择页 ×5(速度/耐力/力量/毅力/智力各 1 张) | 训练类型识别、训练加成解析坐标 | ★★★ |
| 5 | 训练详情:属性增量数字区域 + 支援卡栏特写 | `parse_training_result` / `parse_training_support_card` 坐标 | ★★★ |
| 6 | 凯旋杯特有界面:远征/海外/巴黎训练(如果要做) | 特有流程脚本 | ★★ |
| 7 | 凯旋杯独有事件界面(含选项) | 事件映射 | ★★ |
| 8 | 比赛全流程:赛前 → 马娘列表 → 赛中 → 结果 → 奖励 | 确认是否与现有通用流程一致 | ★★ |
| 9 | 育成结算全流程(等级/因子/历代评分等) | 确认是否与现有通用流程一致 | ★ |
| 10 | 左上角日期区域特写(不同年份各 1 张) | `get_date_img` 坐标 | ★★★ |
| 11 | 距比赛日倒计时区域特写 | `get_turn_to_race_img` 坐标 | ★★ |
| 12 | 技能商店界面 | 确认是否与现有通用(大概率不用改) | ★ |

**截图顺序建议:1 → 3 → 10 → 4 → 5**,这五组就能让 AI 把"训练循环"跑通。

---

## 4. 工作量与风险

### 工作量(素材齐全前提下)
- A 档:约 0.5 天(AI 为主)
- B 档:约 1~2 天(AI 为主,你截图)
- C 档:约 3~7 天(联调为主,需要你配合跑游戏看日志)
- 你的素材采集:1~2 天
- 合计:**1~2 周业余时间**,API 费用估计 100 元上下

### 风险点
1. **凯旋杯是机制最复杂的剧本之一**(海外远征、シナリオリンク、凯旋门赏赛程),比 URA/青春杯都复杂,状态机分支多
2. **像素坐标对分辨率敏感**:截图分辨率必须和项目一致(720x1280),否则全部坐标要重算
3. **国服 UI 与日服可能有差异**:素材必须用国服客户端截,不能抄日服的
4. **事件选项无官方攻略**:只能社区攻略或默认选项先跑
5. 项目后续更新(比如作者自己加了凯旋杯)可能和本地改动冲突

### 最小可行版本(MVP)建议
不要一上来就做全部:先做**"能完整跑完一局育成"**——选剧本 → 训练循环 → 目标赛 → 结算,事件和远征特化后续再加。这样最快见效,风险最低。

---

## 5. 建议路线

1. **每 1~2 周 `git fetch upstream` 检查作者是否更新**(免费,可能作者自己就做了)
2. 决定自己做:按第 3 节顺序收集截图 → 我做 A 档 → 素材到位后做 B 档 → 联调 C 档
3. 联调时需要你:启动游戏 + 模拟器,让工具跑,卡住时截图 + 发日志给我
