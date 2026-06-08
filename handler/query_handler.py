"""消息处理模块 - 关键词触发与序号交互"""

import logging
import time
from typing import Any

from ..cache.post_cache import PostCache
from ..filter.access_control import AccessControl

logger = logging.getLogger(__name__)


class QueryHandler:
    """处理关键词触发和序号交互的查询请求。

    所有 handle_* 方法返回 (handled: bool, reply_text: str | None)，
    由 main.py 统一通过 yield event.plain_result() 发送消息。
    """

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

    def handle_keyword_trigger(
        self,
        user_id: str,
        session_id: str,
        group_id: str,
    ) -> tuple[bool, str | None]:
        """处理关键词触发：返回最近消息列表文本。

        Returns:
            (True, reply_text) — 已处理，文本待发送
            (False, None) — 权限不足未处理
        """
        # 权限检查
        if group_id:
            if not self.access_control.check_group(group_id):
                return False, None
        else:
            if not self.access_control.check_private(user_id):
                return False, None

        # 获取最近消息
        posts = self.cache.get_recent_posts(self.list_count)
        if not posts:
            return True, "暂无消息，请稍后再试。"

        # 构建列表回复
        lines = ["【百分之一 · 最近消息】", ""]
        for i, post in enumerate(posts, 1):
            lines.append(f"{i}. {post.title}")

        lines.append("")
        lines.append(f"回复数字 1-{len(posts)} 查看详情（{self.interaction_timeout}s 内有效）")

        # 记录等待状态
        self._pending_users[session_id] = (user_id, time.time())

        return True, "\n".join(lines)

    def handle_index_reply(
        self,
        user_id: str,
        session_id: str,
        index: int,
    ) -> tuple[bool, str | None]:
        """处理序号回复：返回单条消息详情文本。

        Returns:
            (True, reply_text) — 序号在交互中，文本待发送
            (False, None) — 不在交互中，让 LLM 处理
        """
        # 检查是否在等待状态
        pending = self._pending_users.get(session_id)
        if pending is None:
            return False, None

        pending_user_id, timestamp = pending
        if pending_user_id != user_id:
            return False, None

        # 检查超时
        if time.time() - timestamp > self.interaction_timeout:
            del self._pending_users[session_id]
            return False, None

        # 获取消息详情
        post = self.cache.get_post_by_index(index, self.list_count)
        if post is None:
            return True, None  # 序号无效但确实在交互中，阻止 LLM

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

        return True, "\n".join(lines)
