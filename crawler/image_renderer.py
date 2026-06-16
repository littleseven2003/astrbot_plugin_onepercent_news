"""图片渲染模块 - 将消息内容生成为图片

使用 Pillow 将 PostItem 的有序内容渲染为图片。
"""

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont
from astrbot.api import logger

from .parser import PostItem

# 默认字体路径
FONT_DIR = Path(__file__).parent.parent / "fonts"
DEFAULT_FONT = FONT_DIR / "NotoSansSC-Regular.ttf"

# 图片参数
IMAGE_WIDTH = 800
PADDING = 40
LINE_SPACING = 8
FONT_SIZE = 24
TITLE_FONT_SIZE = 28
TEXT_COLOR = (51, 51, 51)  # #333
TITLE_COLOR = (0, 0, 0)   # #000
BG_COLOR = (255, 255, 255)  # 白色


class ImageRenderer:
    """将 PostItem 渲染为图片"""

    def __init__(self, font_path: str | None = None):
        self.font_path = font_path or str(DEFAULT_FONT)
        self._font = None
        self._title_font = None

    def _get_font(self, size: int = FONT_SIZE) -> ImageFont.FreeTypeFont:
        """获取字体，支持缓存"""
        if size == FONT_SIZE and self._font:
            return self._font
        if size == TITLE_FONT_SIZE and self._title_font:
            return self._title_font

        try:
            font = ImageFont.truetype(self.font_path, size)
            if size == FONT_SIZE:
                self._font = font
            elif size == TITLE_FONT_SIZE:
                self._title_font = font
            return font
        except Exception as e:
            logger.warning(f"加载字体失败: {e}，使用默认字体")
            return ImageFont.load_default()

    async def render_post_to_image(self, post: PostItem) -> BytesIO | None:
        """将 PostItem 渲染为图片，返回 BytesIO 对象"""
        try:
            # 在线程池中执行渲染，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._render_sync, post)
        except Exception as e:
            logger.error(f"渲染图片失败: {e}", exc_info=True)
            return None

    def _render_sync(self, post: PostItem) -> BytesIO:
        """同步渲染方法"""
        # 第一步：计算总高度
        total_height = self._calculate_height(post)

        # 第二步：创建画布
        img = Image.new("RGB", (IMAGE_WIDTH, total_height), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # 第三步：绘制内容
        y = PADDING
        y = self._draw_header(draw, post, y)

        # 绘制有序内容
        if post.ordered_content:
            for seg in post.ordered_content:
                if seg.get("type") == "text":
                    y = self._draw_text_segment(draw, seg["text"], y)
                elif seg.get("type") == "image":
                    y = self._draw_image_segment(img, seg["url"], y)
        elif post.images:
            # 如果没有 ordered_content，使用 images 兜底
            for img_url in post.images:
                y = self._draw_image_segment(img, img_url, y)

        # 第四步：裁剪到实际高度
        if y < total_height:
            img = img.crop((0, 0, IMAGE_WIDTH, y))

        # 第五步：保存到 BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG", quality=95)
        buf.seek(0)
        return buf

    def _calculate_height(self, post: PostItem) -> int:
        """计算图片总高度"""
        height = PADDING  # 顶部内边距

        # 标题高度
        title_font = self._get_font(TITLE_FONT_SIZE)
        title_lines = self._wrap_text(post.title, title_font, IMAGE_WIDTH - 2 * PADDING)
        height += len(title_lines) * (TITLE_FONT_SIZE + LINE_SPACING) + 20

        # 发布时间
        height += FONT_SIZE + 10

        # 原帖链接
        if post.url:
            height += FONT_SIZE + 10

        # 分隔线
        height += 20

        # 有序内容高度
        if post.ordered_content:
            for seg in post.ordered_content:
                if seg.get("type") == "text":
                    height += self._calculate_text_height(seg["text"])
                elif seg.get("type") == "image":
                    height += self._calculate_image_height(seg["url"])
        elif post.images:
            for img_url in post.images:
                height += self._calculate_image_height(img_url)

        height += PADDING  # 底部内边距
        return max(height, 200)  # 最小高度

    def _calculate_text_height(self, text: str) -> int:
        """计算文本段落高度"""
        font = self._get_font(FONT_SIZE)
        lines = self._wrap_text(text, font, IMAGE_WIDTH - 2 * PADDING)
        return len(lines) * (FONT_SIZE + LINE_SPACING) + 10

    def _calculate_image_height(self, url: str) -> int:
        """计算图片高度（估算）"""
        # 简单估算：假设图片宽度为内容宽度，高度按比例计算
        # 实际绘制时会下载图片获取真实尺寸
        return 300  # 默认高度

    def _draw_header(self, draw: ImageDraw.Draw, post: PostItem, y: int) -> int:
        """绘制标题和元信息"""
        title_font = self._get_font(TITLE_FONT_SIZE)
        body_font = self._get_font(FONT_SIZE)

        # 标题
        title_lines = self._wrap_text(post.title, title_font, IMAGE_WIDTH - 2 * PADDING)
        for line in title_lines:
            draw.text((PADDING, y), line, fill=TITLE_COLOR, font=title_font)
            y += TITLE_FONT_SIZE + LINE_SPACING
        y += 10

        # 发布时间
        time_text = f"发布时间: {post.published_at}"
        draw.text((PADDING, y), time_text, fill=TEXT_COLOR, font=body_font)
        y += FONT_SIZE + 10

        # 原帖链接
        if post.url:
            url_text = f"原帖链接: {post.url}"
            draw.text((PADDING, y), url_text, fill=TEXT_COLOR, font=body_font)
            y += FONT_SIZE + 10

        # 分隔线
        y += 10
        draw.line([(PADDING, y), (IMAGE_WIDTH - PADDING, y)], fill=(200, 200, 200), width=2)
        y += 10

        return y

    def _draw_text_segment(self, draw: ImageDraw.Draw, text: str, y: int) -> int:
        """绘制文本段落"""
        font = self._get_font(FONT_SIZE)
        lines = self._wrap_text(text, font, IMAGE_WIDTH - 2 * PADDING)

        for line in lines:
            draw.text((PADDING, y), line, fill=TEXT_COLOR, font=font)
            y += FONT_SIZE + LINE_SPACING

        return y + 10  # 段落间距

    def _draw_image_segment(self, canvas: Image.Image, url: str, y: int) -> int:
        """绘制图片段落"""
        try:
            # 下载图片
            image_data = self._download_image(url)
            if not image_data:
                return y + 10

            # 打开图片
            img = Image.open(BytesIO(image_data))

            # 计算缩放比例，保持宽高比
            max_width = IMAGE_WIDTH - 2 * PADDING
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # 粘贴到画布
            canvas.paste(img, (PADDING, y))

            return y + img.height + 10

        except Exception as e:
            logger.warning(f"绘制图片失败 {url}: {e}")
            return y + 10

    def _download_image(self, url: str) -> bytes | None:
        """下载图片"""
        try:
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.warning(f"下载图片失败 {url}: {e}")
            return None

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """文本自动换行"""
        if not text:
            return []

        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append('')
                continue

            current_line = ''
            for char in paragraph:
                test_line = current_line + char
                # 使用 font.getlength 获取文本宽度
                try:
                    width = font.getlength(test_line)
                except AttributeError:
                    # 兼容旧版 Pillow
                    width = font.getsize(test_line)[0]

                if width <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = char

            if current_line:
                lines.append(current_line)

        return lines


# 全局实例
_renderer: ImageRenderer | None = None


def get_renderer() -> ImageRenderer:
    """获取全局渲染器实例"""
    global _renderer
    if _renderer is None:
        _renderer = ImageRenderer()
    return _renderer


async def render_post_to_image(post: PostItem) -> BytesIO | None:
    """渲染帖子为图片的便捷函数"""
    renderer = get_renderer()
    return await renderer.render_post_to_image(post)
