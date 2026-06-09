"""消息处理模块 - 自动推送新消息（含图片）"""

from typing import Any

from astrbot.api import logger

from ..crawler.parser import PostItem
from ..filter.access_control import AccessControl


class PushHandler:
    """将新消息（文本+图片）推送到配置的目标群聊/私聊。"""

    def __init__(self, context: Any, access_control: AccessControl):
        self.context = context
        self.access_control = access_control

    async def push_new_posts(self, posts: list[PostItem], config: dict):
        push_groups = set(str(g) for g in config.get("push_groups", []))
        push_privates = set(str(p) for p in config.get("push_privates", []))

        if not push_groups and not push_privates:
            return

        for post in posts:
            title_line = f"【百分之一消息】{post.title}"
            if post.url:
                title_line += f"\n查看详情: {post.url}"

            for group_id in push_groups:
                if self.access_control.check_group(group_id):
                    try:
                        await self._send_ordered_post(
                            group_id=group_id, title=title_line, post=post,
                        )
                        logger.info(f"已推送消息到群 {group_id}: {post.title}")
                    except Exception as e:
                        logger.error(f"推送群 {group_id} 失败: {e}")

            for user_id in push_privates:
                if self.access_control.check_private(user_id):
                    try:
                        await self._send_ordered_post(
                            user_id=user_id, title=title_line, post=post,
                        )
                        logger.info(f"已推送消息到用户 {user_id}: {post.title}")
                    except Exception as e:
                        logger.error(f"推送用户 {user_id} 失败: {e}")

    # ---------- sending ----------

    async def _send_ordered_post(self, group_id: str = "", user_id: str = "", title: str = "", post: PostItem = None):
        """使用 ordered_content 按原文顺序发送图文。"""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain, Image

        chain = MessageChain()
        chain_parts = [Plain(text=title)]

        # 优先用 ordered_content，fallback 到 images
        if post and post.ordered_content:
            for seg in post.ordered_content:
                if seg.get("type") == "text":
                    chain_parts.append(Plain(text=seg["text"]))
                elif seg.get("type") == "image":
                    chain_parts.append(Image(seg["url"]))
        elif post and post.images:
            for img_url in post.images:
                chain_parts.append(Image(img_url))

        chain.chain = chain_parts
        target_id = group_id or user_id
        msg_type = "group" if group_id else "private"

        try:
            if hasattr(self.context, "send_message"):
                await self.context.send_message(msg_type, target_id, chain)
                return
        except Exception as e:
            logger.warning(f"context.send_message 失败: {e}")

        try:
            adapter = self._get_adapter()
            if adapter:
                from astrbot.core.platform.astr_message_event import MessageSesion
                session = MessageSesion(session_id=target_id, message_type=msg_type)
                await adapter.send_by_session(session, chain)
                return
        except Exception as e:
            logger.warning(f"适配器发送失败: {e}")

        logger.warning(f"无法发送消息到 {msg_type}/{target_id}")

    def _get_adapter(self):
        try:
            if hasattr(self.context, "platform"):
                return self.context.platform
            if hasattr(self.context, "get_platform_adapter"):
                return self.context.get_platform_adapter()
        except Exception:
            pass
        return None
