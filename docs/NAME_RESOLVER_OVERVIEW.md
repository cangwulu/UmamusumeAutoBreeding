# 统一名称解析层（name_resolver）— 交付概述

> 一劳永逸解决项目中「日文名 / pretty-derby 译名 / BWIKI 官方中文名」三套译名错配问题。

## 解决的问题
原项目里 FuzzyIndex / cosine 散落在 `chara_skills` / `skill_order` / `stud_planner` 等 7 处，阈值还不一致，
导致：
- BWIKI 形态名 `无声无瑕` 与 pretty-derby 形态名 `无声无邪` 对不上；
- 爱丽速子两形态在 BWIKI 与 db.json 里**顺序互换**，按位置对齐会串台；
- FuzzyIndex 单命中返回「递减阈值」而非真实相似度（`无声铃路`→`无声铃` 这种错误召回）。

## 架构
- **规范键 = 日文名**（角色 / 形态 / 卡 / 技能），作为跨源唯一 join 键。
- `resource/umamusume/data/name_index.json`：自举别名表（`by_key` + `alias_to_key`），约 1491 规范键 / 2981 别名。
- `module/umamusume/name_resolver.py`（**不在 `asset/` 下，无 cv2 依赖**）：
  - `get_resolver().canonical(surface) -> (jp_key, score)`
  - 精确别名→1.0；否则全量 cosine 兜底（阈值 0.5，命中即缓存）；失败→`(None, 0)`
  - 另有 `resolve()`（只返键）/ `kind()`（chara|form|card|skill）
- `tools/build_name_index.py`：从 `db.json` + `zh_CN.json` + 各 BWIKI json 聚合别名，**按名对齐形态**（非按位置）。
- `tools/enrich_chara_skills_jp.py`：给 `chara_skills.json` 每张卡加 `card_jp`（日文形态键），可重跑。

## 关键语义
- BWIKI `无声无瑕` 与 derby `无声无邪` 是**同一 JP 形态** `サイレントイノセンス`，→ 都命中 derby「无声无邪」卡是**正确**的。
- 验证「多形态不同技能」必须对比 derby 里**不同** form key（如 `无声无邪` vs `波浪间的绿宝石`）。
- resolver 的 form key 与 `chara_skills.card_jp` **逐字相等**，所以形态解析精确无误（含 `Lunatic Lab` / `波間のエメラルド` 等）。

## 试点接入（已 green）
| 模块 | 接入点 | 状态 |
|---|---|---|
| `chara_skills.py` | `match()` 优先走 resolver | ✅ |
| `skill_order.py` | derby 兜底经 resolver | ✅ |
| `stud_planner.py` | `_resolve_form_card()` 经 resolver | ✅ |

回归：`tools/regress_name_resolver.py`（importlib 绕 cv2，21 项断言全 PASS）。
示例报告：`docs/stud_planner_example.md`（爱丽速子两形态、无声铃鹿两形态技能均正确区分）。

## 待办（deferred，用户选「先建核心+试点」）
将 `affinity` / `event_db` / `race_bwiki` / `support_events` 4 处旧 FuzzyIndex 替换为 `get_resolver().canonical`。

## 运行方式
```bash
# 重建别名表（数据有更新时）
python tools/build_name_index.py
python tools/enrich_chara_skills_jp.py
# 跑回归
python tools/regress_name_resolver.py
# 在自己库存上跑规划器
python module/umamusume/asset/stud_planner.py --venue 中山 --distance 2500 --track 草地 --direction 右 --weather 晴 --condition 良 --style 差
```
