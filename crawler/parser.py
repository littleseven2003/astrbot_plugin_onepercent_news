"""爬虫模块 - 响应解析器

支持的输入来源（按优先级）：
1. __NEXT_DATA__ → Next.js SSR 内嵌数据
2. TapTap WebAPIV2 JSON 响应（从网络拦截捕获）
3. 已渲染的 HTML DOM（Playwright 页面内容）
4. 原始 HTML（httpx 兜底）
"""

import json
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import logger
from bs4 import BeautifulSoup


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

    def parse(self, responses: list[dict[str, Any]]) -> list[PostItem]:
        """依次尝试每个响应源，返回首次成功解析的结果。

        Args:
            responses: TapTapClient.fetch_user_moments() 返回的响应列表，
                       每个元素为 {"url": str, "body": dict|str}

        Returns:
            解析后的 PostItem 列表
        """
        for resp in responses:
            body = resp.get("body")
            if not body:
                continue

            posts = self._try_parse(body, resp.get("url", ""))
            if posts:
                logger.info(f"成功从 {resp.get('url', 'unknown')} 解析到 {len(posts)} 条帖子")
                return posts

        logger.warning("所有响应源均解析失败")
        return []

    def _try_parse(self, body: Any, source_url: str) -> list[PostItem]:
        """根据 body 类型选择解析策略"""
        if isinstance(body, dict):
            return self._parse_dict(body, source_url)
        elif isinstance(body, str):
            return self._parse_string(body)
        return []

    def _parse_dict(self, data: dict, source_url: str) -> list[PostItem]:
        """解析 JSON dict（__NEXT_DATA__ 或 API 响应）"""

        # __NEXT_DATA__ 结构：props.pageProps.{moments, list, posts, ...}
        if "props" in data:
            # Next.js 数据结构
            page_props = data.get("props", {}).get("pageProps", {})
            # 尝试多种可能的键
            for key in ("moments", "list", "posts", "data", "feeds", "items"):
                items = page_props.get(key)
                if isinstance(items, list):
                    return self._parse_items(items)

            # 深度搜索：遍历 pageProps 下的 list
            for val in page_props.values():
                if isinstance(val, dict):
                    items = val.get("list") or val.get("moments") or val.get("data")
                    if isinstance(items, list):
                        return self._parse_items(items)

        # 通用 API 响应结构
        return self._parse_api_response(data)

    def _parse_api_response(self, data: dict) -> list[PostItem]:
        """解析标准 API JSON 响应"""
        # data.list / data.moments / data[]
        for key in ("list", "moments", "items", "data"):
            items = data.get(key)
            if isinstance(items, list):
                return self._parse_items(items)

        # data.data.list 嵌套
        inner = data.get("data")
        if isinstance(inner, dict):
            for key in ("list", "moments", "items"):
                items = inner.get(key)
                if isinstance(items, list):
                    return self._parse_items(items)

        if isinstance(data, list):
            return self._parse_items(data)

        return []

    def _parse_string(self, text: str) -> list[PostItem]:
        """解析 HTML 字符串"""
        # 先尝试从 HTML 中提取 JSON
        soup = BeautifulSoup(text, "lxml")

        # __NEXT_DATA__ script 标签
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag and next_data_tag.string:
            try:
                data = json.loads(next_data_tag.string)
                return self._parse_dict(data, "__NEXT_DATA__")
            except json.JSONDecodeError:
                pass

        # 其他内嵌 JSON script
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string)
                posts = self._parse_api_response(data)
                if posts:
                    return posts
            except (json.JSONDecodeError, AttributeError):
                pass

        # 如果是纯 JSON 字符串
        try:
            data = json.loads(text)
            return self._parse_api_response(data)
        except json.JSONDecodeError:
            pass

        logger.warning("HTML 解析未提取到有效数据")
        return []

    def _parse_items(self, items: list[dict]) -> list[PostItem]:
        """批量解析 item 列表为 PostItem"""
        posts = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # TapTap feed/v7 结构：item 包含 "moment" 嵌套
            if "moment" in item and isinstance(item["moment"], dict):
                item = item["moment"]
            post = self._parse_single_item(item)
            if post:
                posts.append(post)
        return posts

    def _parse_single_item(self, item: dict) -> PostItem | None:
        """从单条数据中提取 PostItem，适配多种字段名"""
        # ID — TapTap 用 id_str
        post_id = str(
            item.get("id_str")
            or item.get("id")
            or item.get("moment_id")
            or item.get("post_id")
            or item.get("feed_id", "")
        )
        if not post_id:
            return None

        # 标题 — 优先从 topic.title 取
        topic = item.get("topic") or {}
        if isinstance(topic, dict):
            title = topic.get("title") or ""
            summary = topic.get("summary") or ""
        else:
            title = ""
            summary = ""

        if not title:
            title = (
                item.get("title")
                or item.get("subject")
                or ""
            )
        if not title:
            # 从 content 取
            content = item.get("content") or item.get("contents") or {}
            if isinstance(content, dict):
                title = content.get("title") or content.get("subject") or ""
        if not title:
            text = item.get("text") or item.get("summary") or item.get("description") or ""
            if isinstance(content, dict):
                text = text or content.get("text", "")
            title = (text[:50] + "...") if len(text) > 50 else text
            title = title or "无标题"

        # 摘要
        if not summary:
            summary = (
                item.get("summary")
                or item.get("description")
                or ""
            )
        if not summary:
            content = item.get("content") or item.get("contents") or {}
            if isinstance(content, dict):
                summary = content.get("text") or content.get("summary", "")
        if summary and len(summary) > 200:
            summary = summary[:200] + "..."

        # URL — TapTap sharing.url
        sharing = item.get("sharing") or {}
        if isinstance(sharing, dict):
            url = sharing.get("url") or ""
        else:
            url = ""
        if not url:
            url = (
                item.get("url")
                or item.get("share_url")
                or item.get("link")
                or ""
            )
        if not url and post_id:
            url = f"https://www.taptap.cn/moment/{post_id}"

        # 发布时间 — TapTap 用 Unix 时间戳 (int)，也可能用字符串
        published_at = self._normalize_time(
            item.get("publish_time")
            or item.get("created_time")
            or item.get("published_at")
            or item.get("create_time")
            or item.get("created_at")
            or item.get("time")
            or ""
        )

        # 图片 — TapTap topic.footer_images.images
        images = self._extract_images(item)

        # 类型
        post_type = (
            item.get("type")
            or item.get("post_type")
            or item.get("moment_type")
            or "normal"
        )

        return PostItem(
            post_id=post_id,
            title=title,
            summary=summary,
            url=url,
            published_at=published_at,
            post_type=post_type,
            images=images,
        )

    def _extract_images(self, item: dict) -> list[str]:
        """从 item 中提取图片 URL 列表（优先取 original_url 获取原图）"""
        images = []

        # 主路径：topic.images[]（TapTap feed/v7 结构）
        topic = item.get("topic") or {}
        if isinstance(topic, dict):
            img_list = topic.get("images") or []
            if isinstance(img_list, list):
                for img in img_list:
                    url = self._extract_img_url(img)
                    if url:
                        images.append(url)

        # 兜底路径 1：footer_images.images
        if not images:
            if isinstance(topic, dict):
                footer = topic.get("footer_images") or {}
                if isinstance(footer, dict):
                    img_list = footer.get("images") or []
                    if isinstance(img_list, list):
                        for img in img_list:
                            url = self._extract_img_url(img)
                            if url:
                                images.append(url)

        # 兜底路径 2：moment 自身的 images
        img_list = item.get("images") or []
        if isinstance(img_list, list):
            for img in img_list:
                url = self._extract_img_url(img)
                if url and url not in images:
                    images.append(url)

        # content.images
        content = item.get("content") or {}
        if isinstance(content, dict):
            content_imgs = content.get("images") or []
            if isinstance(content_imgs, list):
                for img in content_imgs:
                    url = self._extract_img_url(img)
                    if url and url not in images:
                        images.append(url)

        # sharing.image（分享卡片图片，作为最后补充）
        sharing = item.get("sharing") or {}
        if isinstance(sharing, dict):
            share_img = sharing.get("image")
            if share_img:
                url = self._extract_img_url(share_img)
                if url and url not in images:
                    images.append(url)

        # cover（封面图，最低优先级）
        cover = item.get("cover") or {}
        if isinstance(cover, dict):
            cover_img = cover.get("image") or {}
            url = self._extract_img_url(cover_img)
            if url and url not in images:
                images.append(url)

        return images

    @staticmethod
    def _extract_img_url(img: Any) -> str:
        """从各种格式中提取图片 URL，优先取原图（original_url）"""
        if isinstance(img, str):
            return img
        if isinstance(img, dict):
            return (
                img.get("original_url")
                or img.get("url")
                or img.get("large_url")
                or img.get("src")
                or img.get("original")
                or img.get("origin_img")
                or ""
            )
        return ""

    @staticmethod
    def _normalize_time(value: Any) -> str:
        """将各种时间格式统一为 ISO 8601 字符串"""
        from datetime import datetime, timezone

        if not value:
            return ""
        # Unix 时间戳（秒）
        if isinstance(value, (int, float)):
            try:
                dt = datetime.fromtimestamp(value, tz=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            except (OSError, ValueError):
                return str(value)
        return str(value)
