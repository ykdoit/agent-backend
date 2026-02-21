---
name: create_sales_plan
description: 用于在奇绩系统中创建销售行动计划。该技能会自动处理客户验证、联系人匹配、开拓阶段获取及销售动作构建的完整闭环。
---

# 技能：创建销售行动计划 (create_sales_plan)

## 1. 业务流程与工具链依赖
该技能是一个复合流程，必须按以下顺序调用底层 MCP 工具：
1. **[必选]** 调用 `qj_query_customers`：通过 `customer_name` 获取 `id` 和 `code`。
2. **[必选]** 调用 `qj_query_contacts`：传入上一步的 `customer.id` 获取 `contact.id`。
3. **[必选]** 调用 `qj_query_sales_phases`：获取当前计划类型下的 `development_code`。
4. **[必选]** 调用 `qj_get_sales_action_options`：获取动作列表，并根据用户 `action_intent` 匹配出 `levelOne` 和 `levelTwo`。
5. **[最终]** 调用 `qj_create_sales_action_plans`：提交所有信息。

## 2. 槽位清单 (Slots)
| 参数名 | 说明 | 处理要求 |
| :--- | :--- | :--- |
| `customer_name` | 客户名称 | 若模糊匹配到多个，需请用户选择；若未找到，提示确认。 |
| `contact_name` | 联系人姓名 | 必须属于该客户，若找不到则询问。 |
| `plan_date` | 拜访日期 | 必须调用 `time_oracle` 转换为 YYYY-MM-DD。 |
| `time_span` | 时间段 | 严格映射：上午->AM, 下午->PM, 晚上->NIGHT, 未指定->ALL。 |
| `action_intent` | 动作意图 | 需根据 `qj_get_sales_action_options` 的返回结果进行语义匹配。 |

## 3. 状态机详解
### [GATHERING] 信息收集态
- **逻辑**：每轮对话后提取参数。
- **追问准则**：
    - 缺少客户/日期/时间段：直接追问。
    - 示例：“已记录您要拜访华为。请问具体的日期和时间段（上午/下午）是？”
    
### [PENDING] 待确认态 (预览模式)
- **触发**：5 个参数全部集齐，且已完成前置查询（已拿到 ID 和 Code）。
- **强制动作**：输出确认卡片。
- **卡片模板**：
  > ### 📅 销售计划确认
  > - **客户**: {customer_name} ({customer_code})
  > - **拜访人**: {contact_name}
  > - **时间**: {plan_date} {time_span}
  > - **当前阶段**: {phase_name}
  > - **预定动作**: {action_name}
  > 确认提交请回复“确认”，取消请回复“取消”。

### [EXECUTING] 执行态
- **触发**：用户明确表示“确认”、“提交”或“OK”。
- **动作**：调用 `qj_create_sales_action_plans`。

## 4. 核心约束 (Strict Constraints)
- **参数溯源**：`contactId` 必须来自 `qj_query_contacts` 的返回，禁止 Agent 自行编造 UUID。
- **日期禁令**：禁止 Agent 猜测“明天”是哪天，必须经过 `time_oracle` 确认。
- **域账号**：所有接口调用必须透传系统上下文中的 `{staff_domain}`。