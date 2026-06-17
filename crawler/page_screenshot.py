"""页面截图模块 - 使用 Playwright 截取 TapTap 帖子页面

screenshot_session(): 上下文管理器，保持 Chromium 开放，
逐帖截图并立刻通过回调发送，全部完成后自动关闭浏览器。
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Callable, Awaitable

from PIL import Image as PILImage
from astrbot.api import logger

try:
    from playwright.async_api import async_playwright, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright 未安装，页面截图功能不可用")

TAP_MOMENT_URL = "https://www.taptap.cn/moment/{post_id}"

DEFAULT_VIEWPORT = {"width": 800, "height": 800}
DEFAULT_TIMEOUT = 30000

HIDE_FIXED_CSS = """
    *, *::before, *::after {
        animation: none !important;
        transition: none !important;
    }
"""
HIDE_FIXED_JS = """
    () => {
        document.querySelectorAll('*').forEach(el => {
            const cs = getComputedStyle(el);
            if (cs.position === 'fixed' || cs.position === 'sticky') {
                el.style.setProperty('display', 'none', 'important');
            }
        });
    }
"""

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


async def _scroll_to_load(page):
    """逐步滚动页面，触发懒加载图片。"""
    try:
        total_height = await page.evaluate("() => document.body.scrollHeight")
        viewport_height = DEFAULT_VIEWPORT["height"]
        current = 0
        while current < total_height:
            current += viewport_height
            await page.evaluate(f"() => window.scrollTo(0, {current})")
            await asyncio.sleep(0.3)
            new_height = await page.evaluate("() => document.body.scrollHeight")
            if new_height > total_height:
                total_height = new_height
        await page.evaluate("() => window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)
    except Exception as e:
        logger.warning(f"滚动加载图片时出错: {e}")


async def _screenshot_single_page(browser: Browser, post_id: str) -> BytesIO | None:
    """在已有浏览器实例上截取单个帖子，压缩为 JPG 后返回。"""
    url = TAP_MOMENT_URL.format(post_id=post_id)
    page = await browser.new_page(viewport=DEFAULT_VIEWPORT)
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)
        await _scroll_to_load(page)
        await page.add_style_tag(content=HIDE_FIXED_CSS)
        await page.evaluate(HIDE_FIXED_JS)
        await asyncio.sleep(0.5)
        png_bytes = await page.screenshot(full_page=True, type='png')

        # PNG → JPG 压缩（去掉 alpha 通道，大幅缩小文件体积）
        pil_img = PILImage.open(BytesIO(png_bytes))
        if pil_img.mode in ('RGBA', 'LA', 'P'):
            pil_img = pil_img.convert('RGB')
        buf = BytesIO()
        pil_img.save(buf, format='JPEG', quality=85, optimize=True)
        buf.seek(0)
        logger.info(f"✅ 截图成功: {post_id} ({len(buf.getvalue()) // 1024} KB)")
        return buf

    except Exception as e:
        logger.error(f"❌ 截图失败 {post_id}: {e}")
        return None
    finally:
        await page.close()


@asynccontextmanager
async def screenshot_session():
    """截图会话上下文管理器。

    打开 Chromium → yield 截图函数 → 全部完成后自动关闭。

    Usage:
        async with screenshot_session() as screenshot:
            for post in posts:
                buf = await screenshot(post.post_id)
                if buf:
                    await send_image(buf)
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("playwright 未安装")

    await _ensure_chromium()

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-dev-shm-usage']
    )
    logger.info("Playwright 浏览器已启动（截图会话）")

    async def _screenshot(post_id: str) -> BytesIO | None:
        return await _screenshot_single_page(browser, post_id)

    try:
        yield _screenshot
    finally:
        await browser.close()
        await pw.stop()
        logger.info("Playwright 浏览器已关闭（截图会话结束）")


# 保留单帖便捷函数（用于序号交互等场景）
async def capture_post_screenshot(post_id: str) -> BytesIO | None:
    """单帖截图：开 Chromium → 截一张 → 关闭。"""
    async with screenshot_session() as screenshot:
        return await screenshot(post_id)
