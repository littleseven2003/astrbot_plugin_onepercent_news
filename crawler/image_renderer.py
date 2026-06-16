"""图片渲染模块 - 将消息内容生成为图片

使用 Pillow 将 PostItem 的有序内容渲染为图片。
采用两遍式渲染：第一遍收集素材（下载图片、计算尺寸），第二遍实际绘制。
"""

import asyncio
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from astrbot.api import logger

from .parser import PostItem

# 候选中文字体路径（按优先级）
_CANDIDATE_FONTS = [
    Path(__file__).parent.parent / "fonts" / "NotoSansSC-Regular.ttf",
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
]

# 图片参数
IMAGE_WIDTH = 800
PADDING = 40
LINE_SPACING = 8
FONT_SIZE = 24
TITLE_FONT_SIZE = 28
TEXT_COLOR = (51, 51, 51)
TITLE_COLOR = (0, 0, 0)
BG_COLOR = (255, 255, 255)
DIVIDER_COLOR = (200, 200, 200)


def _find_system_font() -> str | None:
    for p in _CANDIDATE_FONTS:
        if p.is_file():
            return str(p)
    return None


def _get_font(size: int = FONT_SIZE) -> ImageFont.FreeTypeFont:
    font_path = _find_system_font()
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as e:
            logger.warning(f"加载系统字体失败 ({font_path}): {e}")
    return ImageFont.load_default()


# ---- 素材结构 ----

@dataclass
class _TextSegment:
    text: str
    lines: list[str] = field(default_factory=list)
    height: int = 0

@dataclass
class _ImageSegment:
    url: str
    pil_image: Image.Image | None = None
    height: int = 0  # 含间距

@dataclass
class _RenderPlan:
    header_height: int = 0
    segments: list = field(default_factory=list)  # _TextSegment | _ImageSegment
    total_height: int = 0


class ImageRenderer:
    """将 PostItem 渲染为图片（两遍式）"""

    def __init__(self):
        self._font = None
        self._title_font = None

    def _get_font(self, size: int = FONT_SIZE) -> ImageFont.FreeTypeFont:
        if size == FONT_SIZE and self._font:
            return self._font
        if size == TITLE_FONT_SIZE and self._title_font:
            return self._title_font
        font = _get_font(size)
        if size == FONT_SIZE:
            self._font = font
        elif size == TITLE_FONT_SIZE:
            self._title_font = font
        return font

    # ---- 公开接口 ----

    async def render_post_to_image(self, post: PostItem) -> BytesIO | None:
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._render_sync, post)
        except Exception as e:
            logger.error(f"渲染图片失败: {e}", exc_info=True)
            return None

    # ---- 第一遍：收集素材 & 计算尺寸 ----

    def _build_plan(self, post: PostItem) -> _RenderPlan:
        plan = _RenderPlan()
        content_width = IMAGE_WIDTH - 2 * PADDING
        title_font = self._get_font(TITLE_FONT_SIZE)
        body_font = self._get_font(FONT_SIZE)

        # 头部
        title_lines = self._wrap_text(post.title, title_font, content_width)
        h = len(title_lines) * (TITLE_FONT_SIZE + LINE_SPACING) + 10
        h += FONT_SIZE + 10  # 发布时间
        if post.url:
            h += FONT_SIZE + 10  # 链接
        h += 20  # 分隔线
        plan.header_height = h

        # 内容段落
        ordered = post.ordered_content
        if not ordered and post.images:
            ordered = [{"type": "image", "url": u} for u in post.images]

        for seg in (ordered or []):
            if seg.get("type") == "text":
                text = (seg.get("text") or "").strip()
                if not text:
                    continue
                lines = self._wrap_text(text, body_font, content_width)
                seg_h = len(lines) * (FONT_SIZE + LINE_SPACING) + 10
                ts = _TextSegment(text=text, lines=lines, height=seg_h)
                plan.segments.append(ts)
            elif seg.get("type") == "image":
                url = seg.get("url") or ""
                if not url:
                    continue
                pil_img = self._download_and_resize(url, content_width)
                seg_h = (pil_img.height + 10) if pil_img else 0
                ims = _ImageSegment(url=url, pil_image=pil_img, height=seg_h)
                plan.segments.append(ims)

        plan.total_height = PADDING + plan.header_height + sum(
            s.height for s in plan.segments
        ) + PADDING
        plan.total_height = max(plan.total_height, 200)
        return plan

    # ---- 第二遍：实际绘制 ----

    def _render_sync(self, post: PostItem) -> BytesIO:
        plan = self._build_plan(post)

        img = Image.new("RGB", (IMAGE_WIDTH, plan.total_height), BG_COLOR)
        draw = ImageDraw.Draw(img)

        y = PADDING
        y = self._draw_header(draw, post, y)

        for seg in plan.segments:
            if isinstance(seg, _TextSegment):
                font = self._get_font(FONT_SIZE)
                for line in seg.lines:
                    draw.text((PADDING, y), line, fill=TEXT_COLOR, font=font)
                    y += FONT_SIZE + LINE_SPACING
                y += 10
            elif isinstance(seg, _ImageSegment):
                if seg.pil_image:
                    img.paste(seg.pil_image, (PADDING, y))
                    y += seg.pil_image.height + 10
                else:
                    y += 10

        # 裁剪到实际高度
        if y < plan.total_height:
            img = img.crop((0, 0, IMAGE_WIDTH, y))

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    # ---- 头部绘制 ----

    def _draw_header(self, draw: ImageDraw.Draw, post: PostItem, y: int) -> int:
        title_font = self._get_font(TITLE_FONT_SIZE)
        body_font = self._get_font(FONT_SIZE)
        content_width = IMAGE_WIDTH - 2 * PADDING

        for line in self._wrap_text(post.title, title_font, content_width):
            draw.text((PADDING, y), line, fill=TITLE_COLOR, font=title_font)
            y += TITLE_FONT_SIZE + LINE_SPACING
        y += 10

        draw.text((PADDING, y), f"发布时间: {post.published_at}", fill=TEXT_COLOR, font=body_font)
        y += FONT_SIZE + 10

        if post.url:
            draw.text((PADDING, y), f"原帖链接: {post.url}", fill=TEXT_COLOR, font=body_font)
            y += FONT_SIZE + 10

        y += 10
        draw.line([(PADDING, y), (IMAGE_WIDTH - PADDING, y)], fill=DIVIDER_COLOR, width=2)
        y += 10
        return y

    # ---- 图片下载 & 缩放 ----

    def _download_and_resize(self, url: str, max_width: int) -> Image.Image | None:
        try:
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
            pil = Image.open(BytesIO(resp.content))
            if pil.width > max_width:
                ratio = max_width / pil.width
                pil = pil.resize((max_width, int(pil.height * ratio)), Image.Resampling.LANCZOS)
            return pil
        except Exception as e:
            logger.warning(f"下载/缩放图片失败 {url[:60]}: {e}")
            return None

    # ---- 文本换行 ----

    @staticmethod
    def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        if not text:
            return []
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append('')
                continue
            current = ''
            for ch in paragraph:
                test = current + ch
                try:
                    w = font.getlength(test)
                except AttributeError:
                    w = font.getsize(test)[0]
                if w <= max_width:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = ch
            if current:
                lines.append(current)
        return lines


# 全局实例
_renderer: ImageRenderer | None = None


def get_renderer() -> ImageRenderer:
    global _renderer
    if _renderer is None:
        _renderer = ImageRenderer()
    return _renderer


async def render_post_to_image(post: PostItem) -> BytesIO | None:
    renderer = get_renderer()
    return await renderer.render_post_to_image(post)
