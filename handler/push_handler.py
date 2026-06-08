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
            text = self._format_text(post)

            for group_id in push_groups:
                if self.access_control.check_group(group_id):
                    try:
                        await self._send_post(group_id=group_id, text=text, images=post.images)
                        logger.info(f"已推送消息到群 {group_id}: {post.title}")
                    except Exception as e:
                        logger.error(f"推送群 {group_id} 失败: {e}")

            for user_id in push_privates:
                if self.access_control.check_private(user_id):
                    try:
                        await self._send_post(user_id=user_id, text=text, images=post.images)
                        logger.info(f"已推送消息到用户 {user_id}: {post.title}")
                    except Exception as e:
                        logger.error(f"推送用户 {user_id} 失败: {e}")

    # ---------- formatting ----------

    @staticmethod
    def _format_text(post: PostItem) -> str:
        lines = ["【百分之一消息】", post.title]
        if post.summary:
            lines.append("")
            s = post.summary
            lines.append(s[:200] + "..." if len(s) > 200 else s)
        if post.url:
            lines.append("")
            lines.append(f"查看详情: {post.url}")
        return "\n".join(lines)

    # ---------- sending ----------

    async def _send_post(self, group_id: str = "", user_id: str = "", text: str = "", images: list[str] | None = None):
        """通过 AstrBot 发送文本 + 图片。"""
        images = images or []
        target_id = group_id or user_id
        msg_type = "group" if group_id else "private"

        try:
            # 方式一：context.send_message（aiocqhttp 标准 API）
            if hasattr(self.context, "send_message"):
                # 合并文本和图片为一条 MessageChain 发送
                from astrbot.api.event import MessageChain
                from astrbot.api.message_components import Plain, Image
                chain = MessageChain()
                chain.chain = [Plain(text=text)] + [
                    Image(url=u) for u in images
                ]
                await self.context.send_message(msg_type, target_id, chain)
                return
        except Exception as e:
            logger.warning(f"context.send_message 失败，尝试 MessageChain: {e}")

        # 方式二：平台适配器 send_by_session（一条 MessageChain）
        try:
            adapter = self._get_adapter()
            if adapter:
                from astrbot.api.event import MessageChain
                from astrbot.api.message_components import Plain, Image
                from astrbot.core.platform.astr_message_event import MessageSesion

                chain = MessageChain()
                chain.chain = [Plain(text=text)] + [
                    Image(url=u) for u in images
                ]

                session = MessageSesion(session_id=target_id, message_type=msg_type)
                await adapter.send_by_session(session, chain)
                return
        except Exception as e:
            logger.warning(f"MessageChain 发送失败: {e}")

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
