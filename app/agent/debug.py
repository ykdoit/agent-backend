"""
调试工具 - 输出完整的系统提示词

使用方法：
    cd /Users/yangkang/agent/backend
    source venv/bin/activate
    python -c "
        import asyncio
        from app.agent.debug import debug_print_system_prompt
        asyncio.run(debug_print_system_prompt(output_file='/tmp/system_prompt.txt'))
    "
    
    cat /tmp/system_prompt.txt
"""
import asyncio
from datetime import datetime
from loguru import logger


async def debug_print_system_prompt(
    session_id: str = "debug",
    output_file: str = None,
    staff_id: str = "debug_user",
    staff_domain: str = "debug_domain",
    staff_name: str = "调试用户",
) -> str:
    """
    调试工具：打印或保存完整的系统提示词
    
    Args:
        session_id: 会话 ID
        output_file: 输出文件路径（可选）
        staff_id: 员工 ID
        staff_domain: 员工域账号
        staff_name: 员工姓名
    
    Returns:
        完整的系统提示词
    """
    from app.agent.manager import get_agent_manager
    
    manager = await get_agent_manager()
    
    # 构建提示词
    sys_prompt = manager._prompt_builder.build_with_defaults(
        staff_id=staff_id,
        staff_domain=staff_domain,
        staff_name=staff_name,
    )
    
    # 统计信息
    char_count = len(sys_prompt)
    token_estimate = char_count // 4
    
    print(f"\n{'='*60}")
    print(f"System Prompt Debug Output")
    print(f"{'='*60}")
    print(f"Session ID:    {session_id}")
    print(f"Character:     {char_count}")
    print(f"Token (估算):  ~{token_estimate}")
    print(f"Generated at:  {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    # 输出到文件
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# System Prompt Debug Output\n")
            f.write(f"# Session: {session_id}\n")
            f.write(f"# Length: {char_count} chars (~{token_estimate} tokens)\n")
            f.write(f"# Generated at: {datetime.now().isoformat()}\n\n")
            f.write("=" * 60 + "\n")
            f.write("SYSTEM PROMPT:\n")
            f.write("=" * 60 + "\n\n")
            f.write(sys_prompt)
        print(f"✅ System prompt saved to: {output_file}\n")
    
    return sys_prompt


async def debug_list_skills():
    """调试工具：列出所有已加载的技能"""
    from app.skill.loader import get_skill_registry
    
    registry = get_skill_registry()
    skills = registry.list_all()
    
    print(f"\n{'='*60}")
    print(f"Loaded Skills ({len(skills)} total)")
    print(f"{'='*60}\n")
    
    for skill in sorted(skills, key=lambda s: s["name"]):
        status = "✅" if skill.get("loaded") else "⏳"
        print(f"{status} {skill['name']}")
        print(f"   {skill['description'][:60]}...")
        print()
    
    return skills


async def debug_load_skill(skill_name: str):
    """调试工具：加载并显示指定技能的详细内容"""
    from app.skill.loader import get_skill_registry
    
    registry = get_skill_registry()
    content = registry.load_skill_detail(skill_name)
    
    print(f"\n{'='*60}")
    print(f"Skill: {skill_name}")
    print(f"{'='*60}\n")
    print(content)
    
    return content


if __name__ == "__main__":
    # 示例用法
    print("Debug Tools for Agent System")
    print("=" * 60)
    print("\n使用方法:")
    print("1. 输出系统提示词:")
    print("   asyncio.run(debug_print_system_prompt(output_file='/tmp/prompt.txt'))")
    print("\n2. 列出所有技能:")
    print("   asyncio.run(debug_list_skills())")
    print("\n3. 加载指定技能:")
    print("   asyncio.run(debug_load_skill('oa-leave'))")
