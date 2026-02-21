"""
PromptBuilder - 系统提示词构建器

负责系统提示词模板管理和占位符填充
"""
from datetime import datetime
from typing import Optional


# 默认系统提示词模板
DEFAULT_SYS_PROMPT = """\
你是一个智能办公助手，能够帮助员工处理各种工作需求。在处理员工需求时，必须遵循以下全局准则：

## 1. 先预览，后执行
凡是涉及"创建"、"提交"、"删除"或"修改"数据的操作，你必须先通过"确认卡片"向用户展示所有参数（如日期、姓名、阶段等），在用户明确回复"确认"、"提交"或"OK"之前，绝对禁止执行最终动作。

## 2. 时间处理规范
- 当用户输入非标准日期（如"明天"、"大后天"、"下周二"）时，必须调用 `time_oracle` 工具解析为标准日期
- 当用户已提供标准格式 YYYY-MM-DD 时，无需调用 `time_oracle`，直接使用
- 禁止自行计算日期偏移，严禁猜测
- 时间段映射：上午/AM→AM，下午/PM→PM，晚上→NIGHT，未指定→ALL（默认）

## 3. 异常处理
- 客户未找到：提示用户确认客户名称
- 时间解析失败：提示用户提供更准确的日期
- 用户取消：检测到"取消"、"算了"时，终止流程并友好告别

{skill_prompt}

请根据用户的请求，理解其意图并选择合适的技能和工具：
- 匹配到技能后，必须严格遵守对应的 SKILL.md 中的【状态机】逻辑
- 在用户未授权前，你的状态必须保持在 [PENDING] 待确认态
- 使用中文回复用户

**系统上下文**：
- 当前员工ID：{staff_id}
- 当前员工域账号：{staff_domain}
- 当前员工姓名：{staff_name}
- 当前日期：{current_date}（{weekday}）
"""


class PromptBuilder:
    """系统提示词构建器"""
    
    # 星期映射
    WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    
    def __init__(self, template: str = DEFAULT_SYS_PROMPT):
        self._template = template
        self._skill_prompt = ""
    
    def set_skill_prompt(self, skill_prompt: str) -> "PromptBuilder":
        """设置技能提示词"""
        self._skill_prompt = skill_prompt
        return self
    
    def build(
        self,
        staff_id: Optional[str] = None,
        staff_domain: Optional[str] = None,
        staff_name: Optional[str] = None,
    ) -> str:
        """构建完整的系统提示词
        
        Args:
            staff_id: 员工ID
            staff_domain: 员工域账号
            staff_name: 员工姓名
        
        Returns:
            填充后的系统提示词
        """
        now = datetime.now()
        
        return self._template.format(
            skill_prompt=self._skill_prompt,
            staff_id=staff_id or "unknown",
            staff_domain=staff_domain or "unknown",
            staff_name=staff_name or "用户",
            current_date=now.strftime("%Y-%m-%d"),
            weekday=self.WEEKDAY_NAMES[now.weekday()],
        )
    
    def build_with_defaults(
        self,
        staff_id: Optional[str] = None,
        staff_domain: Optional[str] = None,
        staff_name: Optional[str] = None,
        default_domain: str = "unknown",
    ) -> str:
        """构建系统提示词（带默认值）
        
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
