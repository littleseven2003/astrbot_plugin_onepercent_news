"""爬虫模块 - TapTap 数据获取

使用 Playwright 无头浏览器访问 TapTap 获取 session，
然后通过页面内 fetch 调用公开 API 获取用户动态数据。

确认可用的 API 端点：
  GET /webapiv2/feed/v7/by-user?user_id={uid}&from=0&limit=20&X-UA={x_ua}
"""

import asyncio
import logging
import json
from typing import Any
from urllib.parse import quote

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# TapTap WebApp 设备标识
X_UA = quote("V=1&PN=WebApp&VN=0.1.0&LANG=zh_CN&PLT=PC")
TAP_BASE = "https://www.taptap.cn"
API_USER_FEED = "/webapiv2/feed/v7/by-user"


class TapTapClient:
    """使用 Playwright 无头浏览器获取 TapTap 用户动态。

    策略：
    1. Playwright 打开 TapTap 首页建立浏览器 session
    2. 在页面上下文中 fetch API（继承浏览器的 Cookie/Headers）
    3. 失败时回退到 httpx 直接请求
    """

    def __init__(
        self,
        uid: str = "19675784",
        user_agent: str = "",
        timeout: int = 30,
        retry: int = 1,
    ):
        self.uid = uid
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        )
        self.timeout = timeout
        self.retry = retry

    async def fetch_user_moments(self) -> list[dict[str, Any]]:
        """获取用户动态原始数据。

        Returns:
            API 响应列表，每个元素为 {"url": str, "body": dict}
        """
        results: list[dict[str, Any]] = []

        # 策略一：Playwright + 页面内 fetch
        for attempt in range(self.retry + 1):
            try:
                results = await self._fetch_via_playwright()
                if results:
                    return results
                logger.warning(f"Playwright 未获取到数据 (attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"Playwright 失败 (attempt {attempt + 1}): {e}")
            if attempt < self.retry:
                await asyncio.sleep(2 ** (attempt + 1))

        # 策略二：httpx 直接请求
        logger.info("尝试 httpx 直接请求...")
        fallback = await self._fetch_via_httpx()
        if fallback:
            results.append(fallback)

        return results

    async def _fetch_via_playwright(self) -> list[dict[str, Any]]:
        """Playwright 获取 session 后调 API"""
        api_url = f"{TAP_BASE}{API_USER_FEED}?user_id={self.uid}&from=0&limit=20&X-UA={X_UA}"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            try:
                # 先访问首页建立 session
                await page.goto(TAP_BASE, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1)

                # 页面内 fetch API
                result = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const r = await fetch("{api_url}");
                            if (!r.ok) return {{ error: 'HTTP ' + r.status }};
                            return await r.json();
                        }} catch(e) {{
                            return {{ error: e.message }};
                        }}
                    }}
                """)

                if isinstance(result, dict) and "error" in result:
                    logger.warning(f"API 返回错误: {result['error']}")
                elif isinstance(result, dict):
                    logger.info(f"成功获取 API 数据")
                    return [{"url": api_url, "body": result}]

            except Exception as e:
                logger.error(f"Playwright fetch 异常: {e}")
            finally:
                await browser.close()

        return []

    async def _fetch_via_httpx(self) -> dict[str, Any] | None:
        """httpx 直接请求（兜底）"""
        api_url = f"{TAP_BASE}{API_USER_FEED}?user_id={self.uid}&from=0&limit=20&X-UA={X_UA}"
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Referer": f"https://www.taptap.cn/user/{self.uid}/moment",
        }
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(api_url, headers=headers)
                r.raise_for_status()
                data = r.json()
                return {"url": api_url, "body": data}
        except Exception as e:
            logger.error(f"httpx 请求失败: {e}")
            return None
