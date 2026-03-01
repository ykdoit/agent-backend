---
name: sales-plan-create
description: 当用户提到创建销售计划、拜访客户、销售行动计划、安排拜访时触发此技能。用于创建新的销售行动计划，记录销售人员对客户的拜访计划和执行动作。这是一个复杂的多步骤流程，需要依次调用5个MCP工具。
---

# 技能：创建销售行动计划

## 1. 业务流程

**5步工具链**（必须按顺序执行）：

```
Step 1: qj_query_customers
  → 获取 customer.id 和 customer.code

Step 2: qj_query_contacts
  → 获取 contact.id

Step 3: qj_query_sales_phases
  → 获取 development_code

Step 4: qj_get_sales_action_options
  → 获取销售动作列表

Step 5: qj_create_sales_action_plans
  → 创建计划
```

## 2. 槽位清单

| 参数 | 说明 | 必填 | 来源 |
|------|------|:----:|------|
| customer_name | 客户名称 | ✅ | 用户输入 |
| contact_name | 联系人姓名 | ✅ | 用户选择 |
| plan_date | 计划日期 | ✅ | time_oracle 解析 |
| time_span | 时间段 | ✅ | AM/PM/ALL/NIGHT |
| place | 拜访地点 | ✅ | 用户输入 |
| action_intents | 销售动作 | ✅ | 用户选择 |

## 3. 状态机

### [GATHERING] 信息收集态

**Step 1：查询客户**
```
用户：明天下午拜访华为的张总
Agent：（调用 qj_query_customers，搜索"华为"）
找到 2 个客户：
1. 华为技术有限公司
2. 华为终端有限公司
请问是哪个客户？
```

**Step 2：查询联系人**
```
用户：第一个
Agent：（调用 qj_query_contacts，搜索"张总"）
找到 1 个联系人：
1. 张伟 - 技术总监
确认拜访此人？
```

**Step 3：查询销售阶段**
```
用户：确认
Agent：（调用 qj_query_sales_phases）
（自动获取阶段信息，不展示给用户）
```

**Step 4：查询销售动作**
```
用户：（继续）
Agent：（调用 qj_get_sales_action_options）
请问计划执行哪些销售动作？
1. 产品介绍
   - 演示产品
   - 讲解方案
2. 技术交流
3. 需求沟通
   - 电话沟通
   - 现场沟通
4. 商务宴请
5. 合同谈判
```

**Step 5：收集其他信息**
```
用户：产品介绍和技术交流
Agent：请问拜访地点是？
用户：华为深圳总部
```

### [PENDING] 待确认态
**确认卡片模板**：
```
📋 销售计划确认

• 客户：{customer_name} ({customer_code})
• 拜访人：{contact_name}
• 时间：{plan_date} {time_span}
• 地点：{place}
• 销售动作：
  - {action_1}
  - {action_2}

确认提交请回复"确认"，取消请回复"取消"
```

### [EXECUTING] 执行态
**任务**：调用 `qj_create_sales_action_plans`

**调用参数**：
```json
{
  "param": {
    "staffDomain": "{staff_domain}",
    "customerCode": "{customer_code}",
    "contactId": "{contact_id}",
    "developmentCode": {development_code},
    "time": "{plan_date}",
    "timeSpan": "{time_span}",
    "place": "{place}",
    "salesEvents": [
      {
        "levelOne": "{action_code}",
        "levelOneName": "{action_name}",
        "levelTwo": "{sub_action_code}"
      }
    ],
    "status": 2
  }
}
```

**成功响应**：
```
✅ 销售行动计划创建成功

计划ID：{plan_id}
时间：{plan_date} {time_span}
客户：{customer_name}

请按时执行，祝您拜访顺利！
```

## 4. 核心约束

### 4.1 字段来源规则
| 字段 | 必须来自 |
|------|----------|
| customerCode | qj_query_customers 返回的 **code**（不是 id） |
| contactId | qj_query_contacts 返回的 **id** |
| developmentCode | qj_query_sales_phases 返回的 **code** |
| salesEvents | qj_get_sales_action_options 构建的数组 |

### 4.2 参数溯源
- **禁止** Agent 自行编造任何 ID
- 所有 ID 必须从 MCP 接口返回

### 4.3 时间处理
- 非标准日期**必须**调用 `time_oracle` 解析
- **禁止**自行计算日期偏移

## 5. 示例对话

**完整流程**：
```
用户：帮我明天下午拜访华为的张总
Agent：找到 2 个华为相关客户：
1. 华为技术有限公司
2. 华为终端有限公司
请问是哪个？

用户：第一个
Agent：找到 1 个联系人：
1. 张伟 - 技术总监
确认拜访此人？

用户：确认
Agent：请问计划执行哪些销售动作？
1. 产品介绍
2. 技术交流
...

用户：产品介绍和技术交流
Agent：请问拜访地点是？

用户：华为深圳总部
Agent：
📋 销售计划确认

• 客户：华为技术有限公司 (KH001)
• 拜访人：张伟
• 时间：2026-02-27 PM
• 地点：华为深圳总部
• 销售动作：
  - 产品介绍
  - 技术交流

确认提交请回复"确认"，取消请回复"取消"

用户：确认
Agent：✅ 销售行动计划创建成功！计划ID：AP20260227001
```

## 6. 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| 客户未找到 | 提示确认客户名称 |
| 联系人未找到 | 提示更换搜索关键词 |
| 时间解析失败 | 要求提供准确日期 |
| 网络错误 | 提示稍后重试 |

## 7. 工具链依赖图

```
qj_query_customers (customer.code)
    ↓
qj_query_contacts (contact.id)
    ↓
qj_query_sales_phases (development.code)
    ↓
qj_get_sales_action_options (salesEvents)
    ↓
qj_create_sales_action_plans (最终提交)
```
