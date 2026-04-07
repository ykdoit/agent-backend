"""
Web Search Tool - 联网搜索工具

提供互联网搜索能力，让 Agent 能获取实时信息。
"""
from typing import Optional
from loguru import logger


def web_search(query: str, max_results: int = 5) -> str:
    """
    搜索互联网获取实时信息

    当用户询问实时信息（新闻、天气、股价、最新技术等）时调用此工具。

    Args:
        query: 搜索关键词，如"今天新闻"、"Python最新版本"、"北京天气"
        max_results: 返回结果数量，默认5条

    Returns:
        搜索结果文本，包含标题、摘要和链接
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return "错误：未安装 ddgs 库，请运行: pip install ddgs"

    try:
        logger.info(f"[web_search] Searching: {query}")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return f"未找到关于「{query}」的相关信息。"

        # 格式化结果
        output_lines = [f"🔍 搜索「{query}」的结果：\n"]

        for i, r in enumerate(results, 1):
            title = r.get('title', '无标题')
            body = r.get('body', '无摘要')
            href = r.get('href', '')

            output_lines.append(f"【{i}】{title}")
            output_lines.append(f"   {body}")
            if href:
                output_lines.append(f"   链接: {href}")
            output_lines.append("")

        result = "\n".join(output_lines)
        logger.info(f"[web_search] Found {len(results)} results")
        return result

    except Exception as e:
        logger.error(f"[web_search] Error: {e}")
        return f"搜索失败：{str(e)}"


def web_search_news(query: str, max_results: int = 5) -> str:
    """
    搜索新闻获取最新资讯

    专门用于搜索新闻类信息，结果更聚焦于新闻报道。

    Args:
        query: 新闻搜索关键词
        max_results: 返回结果数量，默认5条

    Returns:
        新闻搜索结果
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return "错误：未安装 ddgs 库"

    try:
        logger.info(f"[web_search_news] Searching news: {query}")

        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results))

        if not results:
            return f"未找到关于「{query}」的新闻。"

        output_lines = [f"📰 新闻搜索「{query}」：\n"]

        for i, r in enumerate(results, 1):
            title = r.get('title', '无标题')
            body = r.get('body', '无摘要')
            source = r.get('source', '')
            date = r.get('date', '')
            url = r.get('url', '')

            output_lines.append(f"【{i}】{title}")
            if source:
                output_lines.append(f"   来源: {source} {date}")
            output_lines.append(f"   {body}")
            if url:
                output_lines.append(f"   链接: {url}")
            output_lines.append("")

        return "\n".join(output_lines)

    except Exception as e:
        logger.error(f"[web_search_news] Error: {e}")
        return f"新闻搜索失败：{str(e)}"
