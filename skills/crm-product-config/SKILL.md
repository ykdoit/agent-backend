---
name: crm-product-config
description: 当用户提到产品选配、配置产品、选配器、报价方案、产品配置时触发此技能。用于查询CRM系统中的产品信息并进行选配，生成产品配置方案。
---

# 技能：产品选配

## 1. 业务流程

**3步工具链**（必须按顺序执行）：

```
Step 1: crm-query-price-list
  → 获取 priceListId

Step 2: crm-query-product-type
  → 获取 productTypeId

Step 3: crm-query-product-type-goods
  → 获取物料清单
```

## 2. 槽位清单

| 参数 | 说明 | 必填 | 来源 |
|------|------|:----:|------|
| price_list_id | 价目表ID | ✅ | Step 1 返回 |
| product_type_id | 产品型号ID | ✅ | Step 2 返回 |
| search_key | 搜索关键词 | ❌ | 用户输入 |

## 3. 状态机

### [PRICE_LIST] 价目表选择态

**Step 1：查询价目表**

**调用参数**：
```json
{
  "staffDomain": "{staff_domain}"
}
```

**成功响应**：
```
💰 可用价目表

1. **{price_list_name}** (ID: {price_list_id})
2. ...

请问使用哪个价目表？
```

### [PRODUCT_TYPE] 产品型号选择态

**Step 2：查询产品型号**

**调用参数**：
```json
{
  "queryDto": {
    "priceListId": "{price_list_id}",
    "searchKey": "{search_key}",
    "staffDomain": "{staff_domain}"
  }
}
```

**成功响应**：
```
🔍 产品型号查询结果

1. **{product_name}** ({product_series})
   - 标签：{tag}
   - 说明：{description}
   - ID：{product_type_id}

2. ...

请问选择哪个产品型号？
```

### [PRODUCT_GOODS] 物料选择态

**Step 3：查询物料清单**

**调用参数**：
```json
{
  "queryDto": {
    "priceListId": "{price_list_id}",
    "productTypeId": "{product_type_id}",
    "staffDomain": "{staff_domain}"
  }
}
```

**成功响应模板**：
```
📦 产品选配清单

产品：{product_name}

## 核心配置（必选）
1. **{material_group_1}**
   - {material_name} - {spec} - ¥{price}
   - ...

## 可选配置
2. **{material_group_2}**
   - {material_name} - {spec} - ¥{price}
   - ...

---

总价估算：¥{total_price}

需要调整配置吗？或者确认此方案？
```

### [CONFIRMING] 确认态
**任务**：用户确认选配方案

**确认响应**：
```
✅ 产品选配方案确认

产品：{product_name}
核心配置：
- {config_1}
- {config_2}

可选配置：
- {config_3}

总价：¥{total_price}

方案已记录，可用于后续报价。
```

## 4. 核心约束

### 4.1 工具链顺序
- **必须**按顺序调用：价目表 → 产品型号 → 物料清单
- 每个 Step 的 ID 是下一步的必需参数

### 4.2 ID 传递规则
| 字段 | 来源 | 用途 |
|------|------|------|
| priceListId | crm-query-price-list | Step 2 & 3 |
| productTypeId | crm-query-product-type | Step 3 |

### 4.3 搜索规则
- `searchKey` 支持模糊搜索（至少输入 3 位）
- 产品名称、系列、标签都可以作为搜索关键词

## 5. 示例对话

**完整流程**：
```
用户：帮我选配一个服务器
Agent：💰 可用价目表

1. 企业版价目表
2. 个人版价目表
3. 教育版价目表

请问使用哪个价目表？

用户：企业版
Agent：🔍 产品型号查询结果

1. **旗舰型服务器** (X系列)
   - 标签：热销
   - 说明：高端配置

2. **标准型服务器** (Y系列)
   - 标签：推荐
   - 说明：性价比高

3. **入门型服务器** (Z系列)
   - 标签：新品
   - 说明：经济实惠

请问选择哪个产品型号？

用户：旗舰型
Agent：📦 产品选配清单

产品：旗舰型服务器

## 核心配置（必选）
1. **处理器**
   - 高性能处理器 - 32核 - ¥30,000

2. **内存**
   - DDR5内存 - 128GB - ¥15,000

## 可选配置
1. **存储**
   - 1TB SSD - ¥8,000
   - 2TB SSD - ¥15,000

2. **显卡**
   - RTX 4080 - ¥12,000
   - RTX 4090 - ¥18,000

---

基础总价：¥45,000

需要添加可选配置吗？

用户：加个2TB SSD
Agent：✅ 产品选配方案确认

产品：旗舰型服务器

核心配置：
- 高性能处理器 (32核) - ¥30,000
- DDR5内存 (128GB) - ¥15,000

可选配置：
- 2TB SSD - ¥15,000

总价：¥60,000

方案已记录。
```

## 6. 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| 无可用价目表 | 提示"您暂无价目表权限" |
| 产品型号未找到 | 提示"未找到相关产品，请更换关键词" |
| 物料清单为空 | 提示"该产品暂无可选配物料" |
| 网络错误 | 提示稍后重试 |

## 7. 工具链依赖图

```
crm-query-price-list (priceListId)
    ↓
crm-query-product-type (productTypeId)
    ↓
crm-query-product-type-goods (物料清单)
```
