---
name: query_sales_plan_flow
description: 用于查询、检索和查看员工的销售行动计划。支持按时间范围筛选（如“今天”、“下周”、“上个月”），并支持从列表深入查看特定计划的详情。
---

# 技能：查询销售行动计划 (query_sales_plan)

## 1. 业务流程与工具链依赖
该技能涉及两个阶段的检索：
1. **[列表检索]**：调用 `qj_sales_action_plan_list`。根据用户的时间要求（需先经 `time_oracle` 解析）获取计划列表。
2. **[详情获取]**：如果用户指定了某个计划（如“看下第二个”或提供 ID），调用 `qj_get_sales_action_plan_detail` 展示完整动作和拜访细节。

## 2. 槽位清单 (Slots)
| 参数名 | 说明 | 默认值/处理 |
| :--- | :--- | :--- |
| `startTime` | 开始时间 (YYYY-MM-DD HH:mm:ss) | 需经 `time_oracle` 解析，默认为当前日期 00:00:00 |
| `endTime` | 结束时间 (YYYY-MM-DD HH:mm:ss) | 需经 `time_oracle` 解析，默认为 startTime + 30天 |
| `pageNum` | 分页页码 | 默认为 1 |
| `pageSize` | 每页数量 | 默认为 10 |

## 3. 运行逻辑（状态机）

### [FILTERING] 筛选态
- **逻辑**：解析用户的时间意图。
- **示例**：
    - 用户说“我下周有什么安排？” -> Agent 调用 `time_oracle` 获取下周一到周日的范围 -> 填入 `startTime` 和 `endTime`。
    - **约束**：时间区间不能超过 30 天（这是接口 `qj_sales_action_plan_list` 的强制限制）。若超过，需提醒用户缩小范围。

### [PRESENTING] 列表展示态
- **动作**：调用 `qj_sales_action_plan_list`。
- **展示规范**：以列表形式展示 `id`, `customer_name`, `time`, `visit_person`。
- **交互**：询问用户“是否需要查看其中某项计划的详细动作？”

### [DETAILING] 详情态
- **触发**：用户表达查看意图（如“看下华为那个”）。
- **动作**：根据列表返回的 `id` 调用 `qj_get_sales_action_plan_detail`。
- **展示**：展示详细的 `actions` 数组（动作名称、级别）和签到状态。

## 4. 核心约束
- **分页控制**：如果结果超过 10 条，提示用户可以翻页。
- **权限隔离**：必须透传 `{staff_domain}`，确保员工只能查到自己的计划。