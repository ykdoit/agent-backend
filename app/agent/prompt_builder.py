"""
PromptBuilder - 系统提示词构建器（优化版）

特性：
- 只注入技能目录，不注入正文
- 支持动态加载技能详细内容
- 结构化分层设计
"""
from datetime import datetime
from typing import Optional
from loguru import logger


# 默认系统提示词模板
DEFAULT_SYS_PROMPT = """\
# 角色定义

你是一个全能智能助手，可以帮助用户处理任何问题。

## 你擅长的事情
- 🏢 **办公业务**：OA流程、销售管理、客户管理
- 📚 **知识问答**：回答各类知识问题
- 💻 **代码编写**：编写、解释、调试代码
- 📊 **数据分析**：分析数据、生成报告
- ✍️ **创意写作**：撰写文案、邮件、文档
- 🔍 **信息搜索**：搜索互联网获取实时信息

## 工作模式
1. **通用问题**（问答、代码、写作）→ 直接回答，简洁有用
2. **办公业务**（请假、销售计划等）→ 调用技能工具，按流程执行
3. **实时信息**（新闻、天气、股价）→ 调用搜索工具获取
4. **不确定意图** → 先询问澄清

---

# 核心规则

## 1. 技能使用规范
- 当用户**明确要执行办公业务**（请假、出差、销售计划等）时，调用 `read_skill` 读取详细指令
- 通用问题（问答、代码、写作）**直接回答，无需调用技能**
- 不确定时，先询问用户意图

## 2. 办公操作确认
涉及"创建"、"提交"、"删除"、"修改"的**办公业务操作**，必须：
1. 收集所有参数
2. 展示确认卡片给用户
3. 用户明确回复"确认"后执行

## 3. 时间处理规范
- 用户输入"明天"、"下周二" → 调用 `time_oracle` 解析
- 用户已提供 YYYY-MM-DD → 直接使用

## 4. 响应规范
- 使用中文回复
- 保持简洁，避免冗余
- 不确定时主动询问

---

{skill_catalog}

---

# 系统上下文
- 员工ID：{staff_id}
- 员工域账号：{staff_domain}
- 员工姓名：{staff_name}
- 当前日期：{current_date}（{weekday}）
"""


class PromptBuilder:
    """系统提示词构建器"""
    
    WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    
    def __init__(self, template: str = DEFAULT_SYS_PROMPT):
        self._template = template
        self._skill_catalog = ""
    
    def set_skill_catalog(self, catalog: str) -> "PromptBuilder":
        """
        设置技能目录
        
        Args:
            catalog: 技能目录文本（来自 SkillRegistry.get_skill_catalog()）
        
        Returns:
            self（支持链式调用）
        """
        self._skill_catalog = catalog
        return self
    
    def build(
        self,
        staff_id: Optional[str] = None,
        staff_domain: Optional[str] = None,
        staff_name: Optional[str] = None,
    ) -> str:
        """
        构建完整的系统提示词
        
        Args:
            staff_id: 员工ID
            staff_domain: 员工域账号
            staff_name: 员工姓名
        
        Returns:
            填充后的系统提示词
        """
        now = datetime.now()
        
        prompt = self._template.format(
            skill_catalog=self._skill_catalog or "## 可用技能\n\n暂无可用技能。",
            staff_id=staff_id or "unknown",
            staff_domain=staff_domain or "unknown",
            staff_name=staff_name or "用户",
            current_date=now.strftime("%Y-%m-%d"),
            weekday=self.WEEKDAY_NAMES[now.weekday()],
        )
        
        # 输出调试日志
        logger.debug(f"System prompt built: {len(prompt)} chars, ~{len(prompt)//4} tokens")
        logger.debug(f"Skill catalog length: {len(self._skill_catalog)} chars")
        
        return prompt
    
    def build_with_defaults(
        self,
        staff_id: Optional[str] = None,
        staff_domain: Optional[str] = None,
        staff_name: Optional[str] = None,
        default_domain: str = "unknown",
    ) -> str:
        """
        构建系统提示词（带默认值）
        
        Args:
            staff_id: 员工ID
            staff_domain: 员工域账号
            staff_name: 员工姓名
            default_domain: 默认域账号
        
        Returns:
            填充后的系统提示词
        """
        return self.build(
            staff_id=staff_id,
            staff_domain=staff_domain or default_domain,
            staff_name=staff_name,
        )
