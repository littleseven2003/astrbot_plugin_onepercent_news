"""消息处理模块 - 关键词触发与序号交互"""

import logging
import time
from typing import Any

from ..cache.post_cache import PostCache
from ..filter.access_control import AccessControl

logger = logging.getLogger(__name__)


class QueryHandler:
    """处理关键词触发和序号交互的查询请求"""

    def __init__(
        self,
        cache: PostCache,
        access_control: AccessControl,
        config: dict,
    ):
        self.cache = cache
        self.access_control = access_control
        self.list_count = config.get("list_count", 10)
        self.interaction_timeout = config.get("interaction_timeout", 60)

        # 等待序号输入的用户状态: {session_id: (user_id, timestamp)}
        self._pending_users: dict[str, tuple[str, float]] = {}

    async def handle_keyword_trigger(
        self,
        user_id: str,
        session_id: str,
        group_id: str,
        event: Any,
    ):
        """处理关键词触发：回复最近消息列表"""
        # 权限检查
        if group_id:
            if not self.access_control.check_group(group_id):
                return
        else:
            if not self.access_control.check_private(user_id):
                return

        # 获取最近消息
        posts = self.cache.get_recent_posts(self.list_count)
        if not posts:
            await self._reply(event, "暂无消息，请稍后再试。")
            return

        # 构建列表回复
        lines = ["【百分之一 · 最近消息】", ""]
        for i, post in enumerate(posts, 1):
            lines.append(f"{i}. {post.title}")

        lines.append("")
        lines.append(f"回复数字 1-{len(posts)} 查看详情（{self.interaction_timeout}s 内有效）")

        # 记录等待状态
        self._pending_users[session_id] = (user_id, time.time())

        await self._reply(event, "\n".join(lines))

    async def handle_index_reply(
        self,
        user_id: str,
        session_id: str,
        index: int,
        event: Any,
    ):
        """处理序号回复：回复单条消息详情"""
        # 检查是否在等待状态
        pending = self._pending_users.get(session_id)
        if pending is None:
            return

        pending_user_id, timestamp = pending
        if pending_user_id != user_id:
            return

        # 检查超时
        if time.time() - timestamp > self.interaction_timeout:
            del self._pending_users[session_id]
            return

        # 获取消息详情
        post = self.cache.get_post_by_index(index, self.list_count)
        if post is None:
            return

        # 构建详情回复
        lines = [
            f"【{post.title}】",
            "",
        ]
        if post.summary:
            lines.append(post.summary)
            lines.append("")

        lines.append(f"发布时间: {post.published_at}")
        if post.url:
            lines.append(f"原帖链接: {post.url}")

        if post.images:
            lines.append("")
            lines.append(f"图片: {post.images[0]}")
            if len(post.images) > 1:
                for img_url in post.images[1:]:
                    lines.append(f"  {img_url}")

        # 清除等待状态
        del self._pending_users[session_id]

        await self._reply(event, "\n".join(lines))

    async def _reply(self, event: Any, message: str):
        """发送回复消息"""
        try:
            if hasattr(event, "reply"):
                await event.reply(message)
            elif hasattr(event, "send"):
                await event.send(message)
        except Exception as e:
            logger.error(f"回复消息失败: {e}")
