"""页面截图模块 - 使用 Playwright 截取 TapTap 帖子页面

批量模式：收集清单 → 一次性打开 Chromium → 逐帖截图 → 关闭 Chromium。
单帖模式：内部复用批量函数（清单只有 1 项）。
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

DEFAULT_VIEWPORT = {"width": 800, "height": 800}
DEFAULT_TIMEOUT = 30000

# 注入 CSS/JS：隐藏 fixed/sticky 元素
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
    """在已有浏览器实例上截取单个帖子。"""
    url = TAP_MOMENT_URL.format(post_id=post_id)
    page = await browser.new_page(viewport=DEFAULT_VIEWPORT)
    try:
        await page.goto(url, wait_until='networkidle', timeout=DEFAULT_TIMEOUT)
        await _scroll_to_load(page)
        await page.add_style_tag(content=HIDE_FIXED_CSS)
        await page.evaluate(HIDE_FIXED_JS)
        await asyncio.sleep(0.5)
        screenshot_bytes = await page.screenshot(full_page=True, type='png')
        logger.info(f"✅ 截图成功: {post_id}")
        return BytesIO(screenshot_bytes)
    except Exception as e:
        logger.error(f"❌ 截图失败 {post_id}: {e}")
        return None
    finally:
        await page.close()


async def capture_posts_screenshot_batch(post_ids: list[str]) -> dict[str, BytesIO]:
    """批量截图：一次性打开 Chromium，逐帖截图，关闭 Chromium。

    Args:
        post_ids: 需要截图的帖子 ID 列表

    Returns:
        {post_id: BytesIO} 的字典，失败的帖子不在字典中
    """
    if not PLAYWRIGHT_AVAILABLE or not post_ids:
        return {}

    await _ensure_chromium()

    results: dict[str, BytesIO] = {}
    browser = None
    pw = None

    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        logger.info(f"Playwright 浏览器已启动，开始批量截图 ({len(post_ids)} 帖)")

        for pid in post_ids:
            buf = await _screenshot_single_page(browser, pid)
            if buf:
                results[pid] = buf

        logger.info(f"批量截图完成: {len(results)}/{len(post_ids)} 成功")

    except Exception as e:
        logger.error(f"批量截图异常: {e}", exc_info=True)
    finally:
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

    return results


async def capture_post_screenshot(post_id: str) -> BytesIO | None:
    """单帖截图（内部调用批量函数，清单只有 1 项）。"""
    results = await capture_posts_screenshot_batch([post_id])
    return results.get(post_id)
