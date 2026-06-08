"""爬虫模块 - 响应解析器"""

import json
import logging
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class PostItem:
    """统一的消息数据结构"""
    post_id: str
    title: str
    summary: str
    url: str
    published_at: str
    post_type: str = "normal"
    images: list[str] = field(default_factory=list)


class PostParser:
    """解析 TapTap 返回的原始数据，提取 PostItem 列表"""

    def parse(self, raw_text: str) -> list[PostItem]:
        """根据原始文本内容自动选择 JSON 或 HTML 解析。

        Args:
            raw_text: TapTap API 返回的 JSON 字符串或 HTML 页面

        Returns:
            解析后的 PostItem 列表
        """
        if not raw_text:
            return []

        # 尝试 JSON 解析
        try:
            data = json.loads(raw_text)
            return self._parse_json(data)
        except json.JSONDecodeError:
            pass

        # 尝试 HTML 解析
        return self._parse_html(raw_text)

    def _parse_json(self, data: dict) -> list[PostItem]:
        """解析 JSON API 响应，适配 TapTap WebAPIV2 常见结构"""
        posts = []

        # 尝试常见的 JSON 路径
        data_list = (
            data.get("data", {})
            .get("list", [])
        )
        if not data_list:
            data_list = data.get("data", {}).get("moments", [])
        if not data_list:
            data_list = data.get("data", []) if isinstance(data.get("data"), list) else []

        for item in data_list:
            try:
                post = self._parse_item(item)
                if post:
                    posts.append(post)
            except Exception as e:
                logger.warning(f"解析单条消息失败: {e}")

        return posts

    def _parse_html(self, html: str) -> list[PostItem]:
        """解析 HTML 页面，提取帖子列表（兜底方案）"""
        posts = []
        soup = BeautifulSoup(html, "lxml")

        # 尝试提取 __NEXT_DATA__ 中的 JSON
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                return self._parse_json(data)
            except json.JSONDecodeError:
                pass

        # TODO: HTML DOM 解析作为最后兜底
        logger.warning("HTML 解析暂未实现 DOM 提取，返回空列表")
        return posts

    def _parse_item(self, item: dict) -> PostItem | None:
        """从单条 JSON 数据中提取 PostItem"""
        post_id = str(item.get("id") or item.get("moment_id", ""))
        if not post_id:
            return None

        title = item.get("title") or item.get("content", {}).get("title", "")
        if not title:
            # 使用正文前 50 字作为标题
            content_text = item.get("content", {}).get("text", "")
            title = content_text[:50] if content_text else "无标题"

        summary = item.get("summary") or item.get("content", {}).get("text", "")
        if summary and len(summary) > 200:
            summary = summary[:200] + "..."

        url = item.get("url") or item.get("share_url", "")
        if not url and post_id:
            url = f"https://www.taptap.cn/moment/{post_id}"

        published_at = item.get("published_at") or item.get("created_time", "")

        # 提取图片
        images = []
        img_list = item.get("images") or item.get("content", {}).get("images", [])
        if isinstance(img_list, list):
            for img in img_list:
                if isinstance(img, dict):
                    img_url = img.get("url") or img.get("src", "")
                else:
                    img_url = str(img)
                if img_url:
                    images.append(img_url)

        post_type = item.get("type") or item.get("post_type", "normal")

        return PostItem(
            post_id=post_id,
            title=title,
            summary=summary,
            url=url,
            published_at=published_at,
            post_type=post_type,
            images=images,
        )
