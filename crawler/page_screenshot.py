"""页面截图模块 - 使用 Playwright 截取 TapTap 帖子页面

提供将帖子内容截图为长图的功能，用于图片消息模式。
"""

import asyncio
import subprocess
import sys
from io import BytesIO

from astrbot.api import logger

# Playwright 相关导入
try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright 未安装，页面截图功能不可用")

# 帖子页面 URL 模板
TAP_MOMENT_URL = "https://www.taptap.cn/moment/{post_id}"

# 默认浏览器配置
DEFAULT_TIMEOUT = 30000  # 30秒超时
DEFAULT_VIEWPORT = {"width": 1280, "height": 800}

_chromium_installed = False


async def _ensure_chromium():
    """确保 Playwright Chromium 已安装。仅在首次调用时执行。"""
    global _chromium_installed
    if _chromium_installed:
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode == 0:
            logger.info("✅ Playwright Chromium 安装完成")
            _chromium_installed = True
        else:
            err = stderr.decode(errors="ignore").strip()
            logger.warning(f"⚠️ Playwright Chromium 安装失败 (rc={proc.returncode}): {err[:200]}")
    except asyncio.TimeoutError:
        logger.warning("⚠️ Playwright Chromium 安装超时（5分钟）")
    except Exception as e:
        logger.warning(f"⚠️ Playwright Chromium 安装异常: {e}")


class PageScreenshotRenderer:
    """使用 Playwright 截取页面截图"""

    def __init__(self):
        self._browser: Browser | None = None
        self._playwright = None

    async def _ensure_browser(self) -> Browser:
        """确保浏览器实例已启动"""
        if self._browser is not None and self._browser.is_connected():
            return self._browser

        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("playwright 未安装")

        # 先确保 chromium 二进制已安装
        await _ensure_chromium()

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        logger.info("Playwright 浏览器已启动")
        return self._browser

    async def close(self):
        """关闭浏览器实例"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Playwright 浏览器已关闭")

    async def capture_post_screenshot(self, post_id: str) -> BytesIO | None:
        """截取帖子页面的截图"""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("playwright 未安装，无法截取页面")
            return None

        url = TAP_MOMENT_URL.format(post_id=post_id)
        logger.info(f"开始截取页面: {url}")

        try:
            browser = await self._ensure_browser()
            page = await browser.new_page(viewport=DEFAULT_VIEWPORT)

            try:
                await page.goto(url, wait_until='networkidle', timeout=DEFAULT_TIMEOUT)
                await self._wait_for_content(page)

                content_area = await self._find_content_area(page)

                if content_area:
                    screenshot_bytes = await content_area.screenshot(type='png')
                    logger.info(f"✅ 成功截取帖子内容区域: {post_id}")
                else:
                    logger.warning(f"未找到帖子内容区域，截取整个页面: {post_id}")
                    screenshot_bytes = await page.screenshot(full_page=True, type='png')

                return BytesIO(screenshot_bytes)

            finally:
                await page.close()

        except Exception as e:
            logger.error(f"截取页面失败 {post_id}: {e}", exc_info=True)
            return None

    async def _wait_for_content(self, page: Page):
        """等待页面内容加载完成"""
        try:
            await page.wait_for_selector(
                'article, .moment-content, .topic-content, [class*="content"]',
                timeout=10000
            )
        except Exception:
            await asyncio.sleep(2)

    async def _find_content_area(self, page: Page):
        """查找帖子内容区域"""
        selectors = [
            'article',
            '[class*="moment-content"]',
            '[class*="topic-content"]',
            '[class*="post-content"]',
            '[class*="content-detail"]',
            'main',
            '#__next > div > div',
        ]

        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible():
                    box = await element.bounding_box()
                    if box and box['height'] > 100:
                        logger.debug(f"找到内容区域: {selector}")
                        return element
            except Exception:
                continue

        return None


# 全局实例
_screenshot_renderer: PageScreenshotRenderer | None = None


async def get_screenshot_renderer() -> PageScreenshotRenderer:
    """获取全局截图渲染器实例"""
    global _screenshot_renderer
    if _screenshot_renderer is None:
        _screenshot_renderer = PageScreenshotRenderer()
    return _screenshot_renderer


async def capture_post_screenshot(post_id: str) -> BytesIO | None:
    """截取帖子页面截图的便捷函数"""
    renderer = await get_screenshot_renderer()
    return await renderer.capture_post_screenshot(post_id)


async def cleanup():
    """清理全局截图渲染器"""
    global _screenshot_renderer
    if _screenshot_renderer:
        await _screenshot_renderer.close()
        _screenshot_renderer = None
