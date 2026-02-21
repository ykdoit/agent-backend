# 智能办公助手 - 后端服务

基于 AgentScope 的企业级 AI Agent 后端服务，支持流式响应、会话管理和技能扩展。

## 技术栈

- **框架**: FastAPI + Uvicorn
- **Agent**: AgentScope (ReActAgent)
- **存储**: Redis (会话状态、对话历史)
- **协议**: OpenAI 兼容 API + SSE 流式响应

## 目录结构

```
backend/
├── app/
│   ├── agent/              # Agent 核心
│   │   ├── manager.py      # AgentManager 单例
│   │   └── prompt_builder.py
│   ├── api/                # API 路由
│   │   ├── chat.py         # OpenAI 兼容聊天接口
│   │   ├── sessions.py     # 会话管理接口
│   │   └── health.py       # 健康检查
│   ├── core/               # 核心模块
│   │   ├── redis_manager.py    # Redis 状态管理
│   │   └── unified_event_system.py
│   ├── mcp/                # MCP 工具集成
│   │   └── manager.py      # MCP Manager
│   ├── skill/              # 技能系统
│   │   └── loader.py       # 技能加载器
│   ├── main.py             # FastAPI 应用入口
│   └── config.py           # 配置管理
├── skills/                 # 技能配置目录
│   ├── create-sales-plan/  # 销售计划技能
│   └── query-sales-plan/   # 查询销售计划技能
├── config.yml              # 主配置文件
├── .env                    # 环境变量
├── requirements.txt        # Python 依赖
└── run.py                  # 启动脚本
```

## 快速开始

### 环境要求

- Python 3.9+
- Redis 6+

### 安装

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 配置

1. 复制环境变量模板
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件
```env
LLM_API_KEY=your_api_key_here
```

3. 修改 `config.yml`（可选）
```yaml
default_model:
  model_name: glm-4.7
  base_url: https://api.z.ai/api/coding/paas/v4

redis:
  host: localhost
  port: 6379
```

### 启动

```bash
python run.py
```

服务启动后：
- API 地址: http://localhost:8088
- API 文档: http://localhost:8088/docs

## API 接口

### 聊天接口 (OpenAI 兼容)

```bash
POST /v1/chat/completions
Content-Type: application/json

{
  "message": "帮我创建一个销售计划",
  "session_id": "conv_xxx",
  "stream": true
}
```

### 会话管理

```bash
# 创建会话
POST /sessions
{"title": "新对话"}

# 获取会话列表
GET /sessions

# 获取会话详情
GET /sessions/{session_id}

# 删除会话
DELETE /sessions/{session_id}
```

### 健康检查

```bash
GET /health
```

## 核心功能

### 1. 流式响应

支持 SSE 流式输出，实时返回 Agent 响应：

```
data: {"choices":[{"delta":{"content":"正在"}}]}
data: {"choices":[{"delta":{"content":"查询"}}]}
data: [DONE]
```

### 2. 会话管理

- 会话自动创建和持久化
- 对话历史存储（最近 100 条）
- 会话标题 AI 自动生成
- 支持会话恢复

### 3. 技能系统

基于 MD 格式的低代码技能配置：

```
skills/
├── create-sales-plan/
│   ├── SKILL.md          # 技能描述
│   └── skill-config.yaml # 参数配置
```

### 4. MCP 工具集成

支持集成外部 MCP 服务：

- **OA 系统**: 考勤查询、审批流程
- **奇绩 CRM**: 客户管理、销售计划

## 配置说明

### config.yml

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| default_model.model_name | 模型名称 | glm-4.7 |
| default_model.base_url | API 地址 | - |
| redis.host | Redis 主机 | localhost |
| redis.port | Redis 端口 | 6379 |
| skills.dirs | 技能目录 | skills |

### .env

| 变量 | 说明 |
|------|------|
| LLM_API_KEY | 大模型 API 密钥 |

## 开发指南

### 添加新技能

1. 在 `skills/` 下创建目录
2. 编写 `SKILL.md` 描述技能功能
3. 编写 `skill-config.yaml` 配置参数
4. 重启服务自动加载

### 添加 MCP 工具

在 `app/mcp/manager.py` 中注册新工具：

```python
toolkit.create_tool(
    name="qj_query_customers",
    description="查询客户列表",
    handler=your_handler
)
```

## 依赖说明

```
fastapi>=0.100.0
uvicorn>=0.23.0
redis>=4.5.0
agentscope>=0.1.0
pyyaml>=6.0
httpx>=0.24.0
loguru>=0.7.0
```
