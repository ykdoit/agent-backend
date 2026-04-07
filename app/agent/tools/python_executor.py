"""
Python Executor - Python 代码执行沙箱

提供安全的 Python 代码执行能力，支持数据分析、计算等任务。
"""
import sys
import io
import json
import traceback
import base64
from typing import Optional, Dict, Any
from contextlib import redirect_stdout, redirect_stderr
from loguru import logger


def execute_python(
    code: str,
    timeout: int = 30,
    capture_output: bool = True
) -> str:
    """
    执行 Python 代码并返回结果

    用于数据分析、数学计算、文本处理等任务。

    Args:
        code: Python 代码字符串
        timeout: 执行超时时间（秒），默认 30 秒
        capture_output: 是否捕获输出，默认 True

    Returns:
        执行结果文本，包含输出、错误或返回值
    """
    import signal

    # 安全限制：禁止危险操作
    dangerous_keywords = [
        'import os', 'import subprocess', 'import shutil',
        'import sys', '__import__', 'eval(', 'exec(',
        'open(', 'file(', 'input(', 'raw_input(',
        'compile(', 'reload(', 'exit(', 'quit(',
    ]

    code_lower = code.lower()
    for keyword in dangerous_keywords:
        if keyword.lower() in code_lower:
            # 允许一些安全的用法
            if keyword == 'import sys' and 'sys.exit' not in code_lower:
                continue
            if keyword == 'open(' and 'with open' in code_lower:
                # 允许只读文件操作
                continue
            return f"⚠️ 安全限制：禁止使用 `{keyword.strip()}` 操作"

    # 创建执行环境
    exec_globals = {
        '__builtins__': {
            'print': print,
            'len': len,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'sorted': sorted,
            'reversed': reversed,
            'sum': sum,
            'min': min,
            'max': max,
            'abs': abs,
            'round': round,
            'int': int,
            'float': float,
            'str': str,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'bool': bool,
            'type': type,
            'isinstance': isinstance,
            'hasattr': hasattr,
            'getattr': getattr,
            'setattr': setattr,
            'True': True,
            'False': False,
            'None': None,
        },
        'json': json,
        'base64': base64,
    }

    # 尝试导入常用库
    try:
        import math
        exec_globals['math'] = math
    except ImportError:
        pass

    try:
        import random
        exec_globals['random'] = random
    except ImportError:
        pass

    try:
        import datetime
        exec_globals['datetime'] = datetime
    except ImportError:
        pass

    try:
        import re
        exec_globals['re'] = re
    except ImportError:
        pass

    # 尝试导入数据分析库
    try:
        import numpy as np
        exec_globals['np'] = np
        exec_globals['numpy'] = np
    except ImportError:
        pass

    try:
        import pandas as pd
        exec_globals['pd'] = pd
        exec_globals['pandas'] = pd
    except ImportError:
        pass

    # 执行代码
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result = None

    def timeout_handler(signum, frame):
        raise TimeoutError(f"代码执行超时（{timeout}秒）")

    # 设置超时
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)

    try:
        logger.info(f"[execute_python] Executing code ({len(code)} chars)")

        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # 执行代码（使用同一个命名空间）
            exec(code, exec_globals)

        signal.alarm(0)  # 取消超时

        # 收集输出
        stdout_text = stdout_capture.getvalue()
        stderr_text = stderr_capture.getvalue()

        # 格式化结果
        output_parts = []

        if stdout_text:
            output_parts.append(f"📤 输出：\n```\n{stdout_text.strip()}\n```")

        if stderr_text:
            output_parts.append(f"⚠️ 警告：\n```\n{stderr_text.strip()}\n```")

        if result is not None:
            output_parts.append(f"📊 结果：`{result}`")

        if not output_parts:
            output_parts.append("✅ 代码执行成功（无输出）")

        final_output = "\n\n".join(output_parts)
        logger.info(f"[execute_python] Success: {len(final_output)} chars")
        return final_output

    except TimeoutError as e:
        signal.alarm(0)
        logger.error(f"[execute_python] Timeout: {e}")
        return f"⏱️ {str(e)}"

    except Exception as e:
        signal.alarm(0)
        error_msg = traceback.format_exc()
        logger.error(f"[execute_python] Error: {e}\n{error_msg}")
        return f"❌ 执行错误：\n```\n{str(e)}\n```"

    finally:
        signal.signal(signal.SIGALRM, old_handler)


def execute_python_with_plot(code: str, timeout: int = 30) -> str:
    """
    执行 Python 代码并支持生成图表

    支持 matplotlib 绘图，返回 base64 编码的图片。

    Args:
        code: Python 代码字符串
        timeout: 执行超时时间（秒）

    Returns:
        执行结果，包含文本输出和图片（如果有）
    """
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    import matplotlib.pyplot as plt

    # 包装代码以捕获图表
    wrapped_code = f"""
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

{code}

# 检查是否有图表
import io
import base64
buf = io.BytesIO()
if plt.get_fignums():
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    print(f'[IMAGE:data:image/png;base64,{{img_base64}}]')
    plt.close('all')
"""

    return execute_python(wrapped_code, timeout)


def calculate(expression: str) -> str:
    """
    计算数学表达式

    用于简单的数学计算，如 "2+2"、"sqrt(16)" 等。

    Args:
        expression: 数学表达式字符串

    Returns:
        计算结果
    """
    import math

    # 安全的表达式计算
    allowed_names = {
        'sqrt': math.sqrt,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'log': math.log,
        'log10': math.log10,
        'exp': math.exp,
        'pow': pow,
        'abs': abs,
        'round': round,
        'pi': math.pi,
        'e': math.e,
    }

    try:
        # 编译表达式
        code = compile(expression, '<string>', 'eval')

        # 检查名称是否安全
        for name in code.co_names:
            if name not in allowed_names:
                return f"❌ 不允许使用 `{name}`"

        # 计算结果
        result = eval(code, {"__builtins__": {}}, allowed_names)
        return f"📊 计算结果：`{expression} = {result}`"

    except Exception as e:
        return f"❌ 计算错误：{str(e)}"
