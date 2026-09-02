# -*- coding: utf-8 -*-
"""planning: 大赛情报 → 种马规划 的领域服务包（M1）。

组成：
- cup_info    CupService 大赛情报模型 + 持久化 my_inventory/cup_info.json
- inventory   InventoryService 库存校验（包装 asset/stud_planner.load_inventory）
- planner     PlanService 规划（复用 asset/stud_planner 的打分/缺口算法, 不重写）
- cli         统一入口: python -m module.umamusume.planning <cup|plan|check>

数据流: cup(cup_info.json) + inventory(my_inventory/*.csv)
         -> plan -> my_inventory/plan_<date>.md + plan_<date>.json
"""
