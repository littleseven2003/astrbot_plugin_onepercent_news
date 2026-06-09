"""消息处理模块 - 关键词触发与序号交互

返回约定：
  handle_keyword_trigger → (handled: bool, reply_text: str)
  handle_index_reply     → (handled: bool, reply_text: str,
                             ordered_content: list[dict])
    ordered_content 由 main.py 直接用于 event.chain_result()
"""

import time

from astrbot.api import logger

from ..cache.post_cache import PostCache
from ..filter.access_control import AccessControl


class QueryHandler:
    """处理关键词触发和序号交互的查询请求。"""

    def __init__(self, cache: PostCache, access_control: AccessControl, config: dict):
        self.cache = cache
        self.access_control = access_control
        self.list_count = config.get("list_count", 10)
        self.interaction_timeout = config.get("interaction_timeout", 60)
        self._pending_users: dict[str, tuple[str, float]] = {}

    # ---------- 关键词触发（列表） ----------

    def handle_keyword_trigger(
        self, user_id: str, session_id: str, group_id: str,
    ) -> tuple[bool, str]:
        if group_id:
            if not self.access_control.check_group(group_id):
                return False, ""
        else:
            if not self.access_control.check_private(user_id):
                return False, ""

        posts = self.cache.get_recent_posts(self.list_count)
        if not posts:
            return True, "暂无消息，请稍后再试。"

        lines = ["【百分之一 · 最近消息】", ""]
        for i, post in enumerate(posts, 1):
            img_tag = f" ({len(post.images)}图)" if post.images else ""
            lines.append(f"{i}. {post.title}{img_tag}")

        lines.append("")
        lines.append(
            f"回复数字 1-{len(posts)} 查看详情（{self.interaction_timeout}s 内有效）"
        )
        self._pending_users[session_id] = (user_id, time.time())
        return True, "\n".join(lines)

    # ---------- 序号交互（详情 + 有序图文） ----------

    def handle_index_reply(
        self, user_id: str, session_id: str, index: int,
    ) -> tuple[bool, str, list[dict]]:
        """序号回复 → 返回文字摘要 + 有序图文列表。

        Returns: (handled, header_text, ordered_content)
        """
        pending = self._pending_users.get(session_id)
        if pending is None:
            return False, "", []

        pending_user_id, timestamp = pending
        if pending_user_id != user_id:
            return False, "", []

        if time.time() - timestamp > self.interaction_timeout:
            del self._pending_users[session_id]
            return False, "", []

        post = self.cache.get_post_by_index(index, self.list_count)
        if post is None:
            return True, "", []

        # 构建头部摘要
        header = f"【{post.title}】\n\n发布时间: {post.published_at}"
        if post.url:
            header += f"\n原帖链接: {post.url}"

        # 有序内容：优先用 ordered_content，为空则用 images 兜底
        ordered = list(post.ordered_content)
        if not ordered and post.images:
            for img_url in post.images:
                ordered.append({"type": "image", "url": img_url})

        del self._pending_users[session_id]
        return True, header, ordered
