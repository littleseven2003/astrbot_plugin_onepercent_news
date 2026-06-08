"""爬虫模块 - TapTap HTTP 请求封装"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class TapTapClient:
    """TapTap HTTP 请求客户端，仅使用公开 API 和浏览器 UA，不携带 Cookie/Token"""

    # 已知的 TapTap 公开 API 端点
    API_USER_MOMENT_LIST = "/webapiv2/moment/v4/user-moment-list"
    USER_PAGE_URL = "https://www.taptap.cn/user/{uid}/moment"

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

        self._headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"https://www.taptap.cn/user/{uid}",
        }

    async def fetch_user_moments(self) -> str:
        """获取用户动态，优先尝试公开 API，失败则回退到 HTML 页面。

        Returns:
            原始响应文本（JSON 字符串或 HTML）
        """
        # 策略一：尝试公开 API
        api_url = f"https://www.taptap.cn{self.API_USER_MOMENT_LIST}"
        result = await self._request_with_retry(api_url)
        if result:
            return result

        # 策略二：请求用户主页 HTML
        page_url = self.USER_PAGE_URL.format(uid=self.uid)
        result = await self._request_with_retry(page_url)
        if result:
            return result

        raise RuntimeError(f"无法获取 TapTap 用户 {self.uid} 的动态数据")

    async def _request_with_retry(self, url: str) -> str | None:
        """带重试的 HTTP GET 请求，指数退避"""
        last_error = None
        for attempt in range(self.retry + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, headers=self._headers)
                    response.raise_for_status()
                    return response.text
            except Exception as e:
                last_error = e
                logger.warning(
                    f"请求失败 (attempt {attempt + 1}/{self.retry + 1}): {url} - {e}"
                )
                if attempt < self.retry:
                    wait = 2 ** (attempt + 1)
                    await asyncio.sleep(wait)
        logger.error(f"请求最终失败: {url} - {last_error}")
        return None
