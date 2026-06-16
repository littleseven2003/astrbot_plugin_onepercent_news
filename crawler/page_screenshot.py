"""页面截图模块 - 使用 Playwright 截取 TapTap 帖子页面

提供将帖子内容截图为长图的功能，用于图片消息模式。
使用 full_page=True 全页截图，设置视口宽度 800px 使内容自适应。
"""

import asyncio
import sys
from io import BytesIO

from astrbot.api import logger

try:
    from playwright.async_api import async_playwright, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright 未安装，页面截图功能不可用")

TAP_MOMENT_URL = "https://www.taptap.cn/moment/{post_id}"

# 视口宽度 800px，与内容宽度一致；高度无所谓，full_page 会截全页
DEFAULT_VIEWPORT = {"width": 800, "height": 800}
DEFAULT_TIMEOUT = 30000

_chromium_installed = False


async def _ensure_chromium():
    """确保 Playwright Chromium 已安装。首次调用时执行，后续跳过。"""
    global _chromium_installed
    if _chromium_installed:
        return
    if not PLAYWRIGHT_AVAILABLE:
        return

    try:
        logger.info("⏳ 正在检查/安装 Playwright Chromium ...")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode == 0:
            logger.info("✅ Playwright Chromium 就绪")
            _chromium_installed = True
        else:
            err = stderr.decode(errors="ignore").strip()[:200]
            logger.warning(f"⚠️ Playwright Chromium 安装失败 (rc={proc.returncode}): {err}")
    except asyncio.TimeoutError:
        logger.warning("⚠️ Playwright Chromium 安装超时（5分钟）")
    except Exception as e:
        logger.warning(f"⚠️ Playwright Chromium 安装异常: {e}")


class PageScreenshotRenderer:

    def __init__(self):
        self._browser: Browser | None = None
        self._playwright = None

    async def _ensure_browser(self) -> Browser:
        if self._browser is not None and self._browser.is_connected():
            return self._browser

        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwright 未安装")

        await _ensure_chromium()

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        logger.info("Playwright 浏览器已启动")
        return self._browser

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Playwright 浏览器已关闭")

    async def capture_post_screenshot(self, post_id: str) -> BytesIO | None:
        """截取帖子全页长图。视口 800px 宽，full_page=True 截取完整滚动区域。"""
        if not PLAYWRIGHT_AVAILABLE:
            return None

        url = TAP_MOMENT_URL.format(post_id=post_id)
        logger.info(f"开始截取页面: {url}")

        try:
            browser = await self._ensure_browser()
            page = await browser.new_page(viewport=DEFAULT_VIEWPORT)

            try:
                await page.goto(url, wait_until='networkidle', timeout=DEFAULT_TIMEOUT)
                # 等待一小段时间确保动态内容渲染完成
                await asyncio.sleep(1)
                screenshot_bytes = await page.screenshot(full_page=True, type='png')
                logger.info(f"✅ 全页截图成功: {post_id}")
                return BytesIO(screenshot_bytes)
            finally:
                await page.close()

        except Exception as e:
            logger.error(f"截取页面失败 {post_id}: {e}", exc_info=True)
            return None


_screenshot_renderer: PageScreenshotRenderer | None = None


async def get_screenshot_renderer() -> PageScreenshotRenderer:
    global _screenshot_renderer
    if _screenshot_renderer is None:
        _screenshot_renderer = PageScreenshotRenderer()
    return _screenshot_renderer


async def capture_post_screenshot(post_id: str) -> BytesIO | None:
    renderer = await get_screenshot_renderer()
    return await renderer.capture_post_screenshot(post_id)


async def cleanup():
    global _screenshot_renderer
    if _screenshot_renderer:
        await _screenshot_renderer.close()
        _screenshot_renderer = None
