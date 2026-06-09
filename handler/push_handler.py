"""消息处理模块 - 自动推送新消息"""

from typing import Any

from astrbot.api import logger

from ..crawler.parser import PostItem
from ..filter.access_control import AccessControl


class PushHandler:
    """新消息推送：向目标发送标题列表，而不是逐帖详情。"""

    def __init__(self, context: Any, access_control: AccessControl):
        self.context = context
        self.access_control = access_control

    async def push_new_posts(self, posts: list[PostItem], config: dict):
        """推送新消息列表到配置的目标会话。"""
        push_groups = set(str(g) for g in config.get("push_groups", []))
        push_privates = set(str(p) for p in config.get("push_privates", []))

        if not push_groups and not push_privates:
            return

        text = self._format_push_list(posts)

        for group_id in push_groups:
            if self.access_control.check_group(group_id):
                try:
                    await self._send_text(group_id=group_id, text=text)
                    logger.info(
                        f"已推送 {len(posts)} 条新消息标题到群 {group_id}"
                    )
                except Exception as e:
                    logger.error(f"推送群 {group_id} 失败: {e}")

        for user_id in push_privates:
            if self.access_control.check_private(user_id):
                try:
                    await self._send_text(user_id=user_id, text=text)
                    logger.info(
                        f"已推送 {len(posts)} 条新消息标题到用户 {user_id}"
                    )
                except Exception as e:
                    logger.error(f"推送用户 {user_id} 失败: {e}")

    @staticmethod
    def _format_push_list(posts: list[PostItem]) -> str:
        lines = ["【百分之一 · 新消息】", ""]
        for i, post in enumerate(posts, 1):
            img_tag = f" ({len(post.images)}图)" if post.images else ""
            lines.append(f"🆕 {i}. {post.title}{img_tag}")
        lines.append("")
        lines.append("发送 五维消息 查看完整列表与详情")
        return "\n".join(lines)

    async def _send_text(
        self, group_id: str = "", user_id: str = "", text: str = ""
    ):
        """通过 AstrBot Context 发送纯文本消息。

        AstrBot v4.25.5 Context.send_message(target_id, message) -- 2 参数。
        """
        target_id = group_id or user_id

        if hasattr(self.context, "send_message"):
            try:
                await self.context.send_message(target_id, text)
                return
            except Exception as e:
                logger.warning(f"send_message 失败: {e}")

        try:
            adapter = self._get_adapter()
            if adapter:
                from astrbot.api.event import MessageChain
                from astrbot.api.message_components import Plain
                from astrbot.core.platform.astr_message_event import MessageSesion

                chain = MessageChain()
                chain.chain = [Plain(text=text)]
                mtype = "group" if group_id else "private"
                session = MessageSesion(session_id=target_id, message_type=mtype)
                await adapter.send_by_session(session, chain)
                return
        except Exception as e:
            logger.warning(f"适配器发送失败: {e}")

        logger.warning(f"无法发送消息到 {target_id}")

    def _get_adapter(self):
        try:
            if hasattr(self.context, "platform"):
                return self.context.platform
            if hasattr(self.context, "get_platform_adapter"):
                return self.context.get_platform_adapter()
        except Exception:
            pass
        return None
