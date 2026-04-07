"""
Web Fetch Tool - 网页抓取工具

提供网页内容抓取能力，让 Agent 能直接获取网页内容而不是只返回链接。
"""
import re
import httpx
from typing import Optional
from loguru import logger
from bs4 import BeautifulSoup


def fetch_url(url: str, timeout: int = 15) -> str:
    """
    抓取网页内容并返回清理后的文本

    当需要获取某个网页的具体内容时调用此工具。
    会自动清理 HTML 标签、脚本、样式等，只保留正文内容。

    Args:
        url: 网页地址，如 "https://example.com/article"
        timeout: 超时时间（秒），默认 15 秒

    Returns:
        清理后的网页文本内容
    """
    try:
        logger.info(f"[fetch_url] Fetching: {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)

        if response.status_code != 200:
            return f"❌ 请求失败：HTTP {response.status_code}"

        # 解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 移除不需要的元素
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
            element.decompose()

        # 获取标题
        title = soup.title.string.strip() if soup.title else "无标题"

        # 获取正文内容
        # 优先尝试找到 article 或 main 标签
        content_area = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'content|article|post|entry', re.I))

        if content_area:
            text = content_area.get_text(separator='\n', strip=True)
        else:
            text = soup.get_text(separator='\n', strip=True)

        # 清理多余空行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        # 限制长度
        max_length = 5000
        if len(text) > max_length:
            text = text[:max_length] + f"\n\n... (内容过长，已截断，共 {len(text)} 字符)"

        result = f"📄 **{title}**\n\n{text}"
        logger.info(f"[fetch_url] Success: {len(text)} chars from {url}")

        return result

    except httpx.TimeoutException:
        logger.error(f"[fetch_url] Timeout: {url}")
        return f"⏱️ 请求超时：{url}"

    except Exception as e:
        logger.error(f"[fetch_url] Error: {e}")
        return f"❌ 抓取失败：{str(e)}"


def fetch_url_with_links(url: str, timeout: int = 15) -> str:
    """
    抓取网页内容并保留链接

    类似 fetch_url，但会保留网页中的链接信息。

    Args:
        url: 网页地址
        timeout: 超时时间（秒）

    Returns:
        包含链接的网页内容
    """
    try:
        logger.info(f"[fetch_url_with_links] Fetching: {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)

        if response.status_code != 200:
            return f"❌ 请求失败：HTTP {response.status_code}"

        soup = BeautifulSoup(response.text, 'html.parser')

        # 移除不需要的元素
        for element in soup(['script', 'style', 'nav', 'footer', 'iframe', 'noscript']):
            element.decompose()

        title = soup.title.string.strip() if soup.title else "无标题"

        # 提取链接
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if text and href.startswith('http'):
                links.append(f"- [{text}]({href})")

        # 获取正文
        content_area = soup.find('article') or soup.find('main') or soup
        text = content_area.get_text(separator='\n', strip=True)

        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines[:50])  # 限制行数

        # 限制链接数量
        links_text = '\n'.join(links[:20])

        result = f"📄 **{title}**\n\n{text}\n\n🔗 **相关链接：**\n{links_text}"
        logger.info(f"[fetch_url_with_links] Success")

        return result

    except Exception as e:
        logger.error(f"[fetch_url_with_links] Error: {e}")
        return f"❌ 抓取失败：{str(e)}"


def extract_article(url: str, timeout: int = 15) -> str:
    """
    从网页中提取文章内容

    专门用于提取新闻、博客等文章类内容，会自动识别标题、作者、时间等。

    Args:
        url: 文章地址
        timeout: 超时时间（秒）

    Returns:
        结构化的文章内容
    """
    try:
        logger.info(f"[extract_article] Extracting: {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }

        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)

        if response.status_code != 200:
            return f"❌ 请求失败：HTTP {response.status_code}"

        soup = BeautifulSoup(response.text, 'html.parser')

        # 移除干扰元素
        for element in soup(['script', 'style', 'nav', 'aside', 'iframe', 'noscript', 'header', 'footer']):
            element.decompose()

        # 提取标题
        title = ""
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)

        # 提取时间
        time_str = ""
        time_tag = soup.find('time') or soup.find('span', class_=re.compile(r'date|time', re.I))
        if time_tag:
            time_str = time_tag.get_text(strip=True)

        # 提取作者
        author = ""
        author_tag = soup.find('span', class_=re.compile(r'author', re.I)) or soup.find('a', rel='author')
        if author_tag:
            author = author_tag.get_text(strip=True)

        # 提取正文
        article = soup.find('article') or soup.find('div', class_=re.compile(r'article|content|post|entry', re.I))
        if article:
            # 提取段落
            paragraphs = []
            for p in article.find_all(['p', 'h2', 'h3', 'h4']):
                text = p.get_text(strip=True)
                if len(text) > 20:  # 过滤太短的段落
                    paragraphs.append(text)

            content = '\n\n'.join(paragraphs[:30])  # 限制段落数
        else:
            content = soup.get_text(strip=True)[:3000]

        # 组装结果
        parts = [f"📄 **{title}**"]
        if author:
            parts.append(f"✍️ 作者：{author}")
        if time_str:
            parts.append(f"📅 时间：{time_str}")
        parts.append(f"\n{content}")

        result = '\n'.join(parts)
        logger.info(f"[extract_article] Success: {len(content)} chars")

        return result

    except Exception as e:
        logger.error(f"[extract_article] Error: {e}")
        return f"❌ 提取失败：{str(e)}"
