"""
InsightFlow 销售线索模块 - 搜索工具层
文件路径: src/tools/web_search.py

支持多搜索引擎后端:
  - duckduckgo: 完全免费，无需 API key（默认）
  - bocha: 博查搜索 API，便宜且中文质量好
  - tavily: Tavily MCP，质量高但价格贵

通过环境变量 SEARCH_PROVIDER 切换后端。
"""

import asyncio
import json
import os
import re
from typing import Optional

from agentscope.mcp import StdIOStatefulClient, HttpStatelessClient
from agentscope.message import TextBlock
from agentscope.tool import Toolkit, ToolResponse

from src.config import Config


# ── 通用工具：网页正文提取 ─────────────────────────────────────


async def _extract_text_from_url(url: str, max_chars: int = 8000) -> str:
    """用 httpx 抓取网页并提取正文文本（去除 HTML 标签）"""
    import httpx

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return f"提取失败: {e}"

    # 去除 script / style / 注释
    html = re.sub(
        r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    # 去除所有 HTML 标签
    text = re.sub(r"<[^>]+>", " ", html)
    # 合并空白
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > max_chars:
        text = text[:max_chars] + "...(已截断)"

    return text


# ── DuckDuckGo 后端 ────────────────────────────────────────────


def _register_duckduckgo(toolkit: Toolkit) -> None:
    """注册 DuckDuckGo 搜索工具函数到 Toolkit"""

    async def web_search(query: str, max_results: int = 8) -> ToolResponse:
        """搜索互联网获取信息。返回包含标题、URL和摘要的搜索结果列表。

        Args:
            query (str):
                搜索关键词，建议2-6个词。
            max_results (int):
                返回结果数量，最多10条。
        """
        from ddgs import DDGS

        # 防御：LLM 有时传空字符串或非整数
        if not isinstance(max_results, int) or max_results <= 0:
            max_results = 8
        max_results = min(max_results, 10)
        try:
            import random
            import time

            def _sync_ddg_search():
                # 随机延迟 0.5-2 秒，避免 DuckDuckGo 频率限制
                time.sleep(random.uniform(0.5, 2.0))
                with DDGS() as ddgs:
                    raw = list(
                        ddgs.text(query, max_results=max_results, region="cn-zh")
                    )
                    if not raw:
                        # cn-zh 无结果时，去掉 region 重试
                        raw = list(ddgs.text(query, max_results=max_results))
                    if not raw:
                        # 仍无结果，延迟后再试一次
                        time.sleep(random.uniform(1.0, 3.0))
                        raw = list(ddgs.text(query, max_results=max_results))
                    return raw

            raw = await asyncio.to_thread(_sync_ddg_search)
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw
            ]
        except Exception as e:
            results = [{"error": f"搜索失败: {e}"}]

        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=json.dumps(results, ensure_ascii=False, indent=2),
                ),
            ],
        )

    async def web_extract(url: str) -> ToolResponse:
        """提取指定网页的正文内容。用于获取搜索结果中某个页面的详细信息。

        Args:
            url (str):
                要提取内容的网页 URL。
        """
        text = await _extract_text_from_url(url)
        result = {"url": url, "content": text}
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, indent=2),
                ),
            ],
        )

    toolkit.register_tool_function(web_search)
    toolkit.register_tool_function(web_extract)
    print("[Tools] DuckDuckGo 搜索已注册（免费，无需 API Key）")


# ── 博查后端 ───────────────────────────────────────────────────


def _register_bocha(toolkit: Toolkit, api_key: str) -> None:
    """注册博查搜索工具函数到 Toolkit"""

    async def web_search(query: str, max_results: int = 8) -> ToolResponse:
        """搜索互联网获取信息。返回包含标题、URL和摘要的搜索结果列表。

        Args:
            query (str):
                搜索关键词，支持自然语言。
            max_results (int):
                返回结果数量，最多50条。
        """
        import httpx

        # 防御：LLM 有时传空字符串或非整数
        if not isinstance(max_results, int) or max_results <= 0:
            max_results = 8
        max_results = min(max_results, 50)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.bocha.cn/v1/web-search",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": query,
                        "count": max_results,
                        "summary": True,
                        "freshness": "noLimit",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=json.dumps(
                            [{"error": f"博查搜索失败: {e}"}],
                            ensure_ascii=False,
                        ),
                    ),
                ],
            )

        # 从博查响应中提取统一格式
        results = []
        web_pages = data.get("data", {}).get("webPages", {}) or data.get("webPages", {})
        for item in web_pages.get("value", []):
            results.append(
                {
                    "title": item.get("name", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("summary", "") or item.get("snippet", ""),
                    "site_name": item.get("siteName", ""),
                    "date": item.get("datePublished", ""),
                }
            )

        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=json.dumps(results, ensure_ascii=False, indent=2),
                ),
            ],
        )

    async def web_extract(url: str) -> ToolResponse:
        """提取指定网页的正文内容。用于获取搜索结果中某个页面的详细信息。

        Args:
            url (str):
                要提取内容的网页 URL。
        """
        text = await _extract_text_from_url(url)
        result = {"url": url, "content": text}
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, indent=2),
                ),
            ],
        )

    toolkit.register_tool_function(web_search)
    toolkit.register_tool_function(web_extract)
    print("[Tools] 博查搜索已注册（api.bocha.cn）")


# ── Tavily MCP 后端 ────────────────────────────────────────────


async def _register_tavily(
    toolkit: Toolkit,
    api_key: str,
    mcp_clients: list,
) -> None:
    """注册 Tavily MCP 搜索工具到 Toolkit（保持原有逻辑）"""
    tavily_client = StdIOStatefulClient(
        name="tavily_mcp",
        command="npx",
        args=["-y", "tavily-mcp@latest"],
        env={
            "TAVILY_API_KEY": api_key,
            "PATH": os.environ.get("PATH", ""),
        },
    )
    await tavily_client.connect()
    await toolkit.register_mcp_client(
        tavily_client,
        group_name="search_tools",
    )
    mcp_clients.append(tavily_client)
    print("[Tools] Tavily Search MCP 已连接")


# ── 主入口 ─────────────────────────────────────────────────────


async def setup_search_toolkit(
    enable_qcc: bool = True,
) -> tuple[Toolkit, list]:
    """
    初始化搜索工具集

    根据 SEARCH_PROVIDER 环境变量选择搜索后端：
      - duckduckgo: 免费，无需 API key（默认）
      - bocha: 博查搜索 API，需要 BOCHA_API_KEY
      - tavily: Tavily MCP，需要 TAVILY_API_KEY

    企查查 MCP 独立于搜索后端，始终可选启用。

    Args:
        enable_qcc: 是否启用企查查 MCP（需要 QCC_MCP_KEY）

    Returns:
        tuple[Toolkit, list]: (toolkit, mcp_clients) 用于后续关闭
    """
    config = Config()
    toolkit = Toolkit()
    mcp_clients = []

    provider = config.search_provider
    print(f"[Tools] 搜索引擎: {provider}")

    # ── 搜索后端选择 ──────────────────────────────────────────
    if provider == "tavily":
        tavily_api_key = config.tavily_api_key
        if tavily_api_key:
            await _register_tavily(toolkit, tavily_api_key, mcp_clients)
        else:
            print("[Tools] 错误: SEARCH_PROVIDER=tavily 但 TAVILY_API_KEY 未设置")
            print("[Tools] 回退到 DuckDuckGo...")
            _register_duckduckgo(toolkit)

    elif provider == "bocha":
        bocha_api_key = config.bocha_api_key
        if bocha_api_key:
            _register_bocha(toolkit, bocha_api_key)
        else:
            print("[Tools] 错误: SEARCH_PROVIDER=bocha 但 BOCHA_API_KEY 未设置")
            print("[Tools] 回退到 DuckDuckGo...")
            _register_duckduckgo(toolkit)

    elif provider == "duckduckgo":
        _register_duckduckgo(toolkit)

    else:
        print(f"[Tools] 未知搜索引擎: {provider}，使用 DuckDuckGo")
        _register_duckduckgo(toolkit)

    # ── 企查查 MCP（独立于搜索后端）────────────────────────────
    qcc_key = config.qcc_mcp_key
    # 跳过占位符或空 key
    qcc_valid = enable_qcc and qcc_key and qcc_key not in ("your_qcc_mcp_key_here", "")
    if qcc_valid:
        try:
            qcc_client = HttpStatelessClient(
                name="qcc_mcp",
                transport="streamable_http",
                url=f"https://mcp.qcc.com/basic/stream?key={qcc_key}",
            )
            await toolkit.register_mcp_client(
                qcc_client,
                group_name="enterprise_tools",
            )
            mcp_clients.append(qcc_client)
            print("[Tools] 企查查 MCP 已连接")
        except Exception as e:
            print(f"[Tools] 企查查 MCP 连接失败（已跳过）: {e}")
    else:
        if enable_qcc:
            print("[Tools] 提示: QCC_MCP_KEY 未设置或为占位符，企查查企业数据不可用")

    return toolkit, mcp_clients


async def setup_file_toolkit() -> Toolkit:
    """
    初始化文件操作工具（给 Report Writer 使用）

    Returns:
        Toolkit: 包含 save_file 和 read_file 工具的 Toolkit
    """

    async def save_file(content: str, filepath: str) -> ToolResponse:
        """保存文件到指定路径

        Args:
            content (str):
                文件内容。
            filepath (str):
                文件保存路径。
        """
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResponse(
            content=[
                TextBlock(type="text", text=f"文件已保存: {filepath}"),
            ],
        )

    async def read_file(filepath: str) -> ToolResponse:
        """读取文件内容

        Args:
            filepath (str):
                文件路径。
        """
        with open(filepath, "r", encoding="utf-8") as f:
            file_content = f.read()
        return ToolResponse(
            content=[
                TextBlock(type="text", text=file_content),
            ],
        )

    toolkit = Toolkit()
    toolkit.register_tool_function(save_file)
    toolkit.register_tool_function(read_file)
    return toolkit


async def close_mcp_clients(clients: list):
    """关闭所有 MCP 客户端连接"""
    for client in clients:
        try:
            await client.close()
        except Exception as e:
            print(f"[Tools] 关闭 MCP 客户端失败: {e}")
