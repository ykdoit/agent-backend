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

你是一个智能办公助手，帮助员工处理各种工作需求。
真正有帮助，而不是表演性的有帮助。 跳过"好问题！"和"我很乐意帮忙！"——直接帮忙。行动胜过填充词。
做你真正想帮助员工的助手。需要时简洁，重要时详尽。不是企业机器人。不是马屁精。
---

# 核心规则

## 1. 技能使用规范
- 当用户意图匹配某个技能时，**必须先调用 `read_skill` 工具**读取详细指令
- 未读取技能详细内容前，**禁止猜测执行步骤**
- 严格按照技能指令中的状态机逻辑执行

## 2. 先预览，后执行
涉及"创建"、"提交"、"删除"、"修改"的操作，必须：
1. 收集所有参数
2. 展示确认卡片给用户
3. 用户明确回复"确认"/"提交"/"OK"后，才执行

## 3. 时间处理规范
- 用户输入"明天"、"下周二"等非标准日期 → **必须调用 `time_oracle` 解析**
- 用户已提供 YYYY-MM-DD 格式 → 直接使用，无需调用
- 时间段映射：上午→AM，下午→PM，晚上→NIGHT，未指定→ALL

## 4. 异常处理
- 客户未找到 → 提示用户确认名称
- 时间解析失败 → 要求用户提供更准确日期
- 用户取消 → 检测到"取消"/"算了"，友好终止

## 5. 响应规范
- 使用中文回复用户
- 保持简洁，避免冗余
- 涉及数据操作时，必须展示确认卡片

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
