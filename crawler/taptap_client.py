"""爬虫模块 - TapTap 数据获取（httpx 直连）

通过 httpx 直接请求 TapTap 公开 API，携带 X-UA 设备标识。
参照 RSSHub 方案，无需 Playwright/无头浏览器。

API 端点:
  GET /webapiv2/feed/v7/by-user?user_id={uid}&from=0&limit=20&X-UA={x_ua}
"""

import asyncio
import logging
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# TapTap WebApp 设备标识（来源：RSSHub utils.tsx）
X_UA = quote("V=1&PN=WebApp&VN=0.1.0&LANG=zh_CN&PLT=PC")
TAP_BASE = "https://www.taptap.cn"
API_USER_FEED = "/webapiv2/feed/v7/by-user"


class TapTapClient:
    """TapTap 公开 API 客户端。

    使用 httpx + X_UA 查询参数直接访问 TapTap WebAPIV2，
    无需 Cookie、Token 或浏览器 session。
    """

    def __init__(
        self,
        uid: str = "19675784",
        user_agent: str = "",
        timeout: int = 15,
        retry: int = 2,
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
        api_url = f"{TAP_BASE}{API_USER_FEED}?user_id={self.uid}&from=0&limit=20&X-UA={X_UA}"
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Referer": f"https://www.taptap.cn/user/{self.uid}/moment",
        }

        for attempt in range(self.retry + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, follow_redirects=True
                ) as client:
                    r = await client.get(api_url, headers=headers)
                    r.raise_for_status()
                    data = r.json()
                    items = data.get("data", {}).get("list", [])
                    logger.info(
                        f"TapTap API 返回 {len(items)} 条帖子 "
                        f"(attempt {attempt + 1}/{self.retry + 1})"
                    )
                    return [{"url": api_url, "body": data}]
            except Exception as e:
                logger.warning(
                    f"TapTap API 请求失败 (attempt {attempt + 1}/{self.retry + 1}): {e}"
                )
                if attempt < self.retry:
                    await asyncio.sleep(2 ** (attempt + 1))

        logger.error(f"TapTap API 请求最终失败（已重试 {self.retry} 次）")
        return []
