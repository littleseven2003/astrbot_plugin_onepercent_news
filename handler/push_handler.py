"""消息处理模块 - 自动推送新消息"""

from typing import Any

from astrbot.api import logger

from ..crawler.parser import PostItem
from ..filter.access_control import AccessControl


class PushHandler:
    """将新消息推送到配置的目标群聊/私聊。

    AstrBot Context 的消息发送 API 依赖 aiocqhttp 适配器，
    通过 context.get_platform_adapter() 来获取适配器实例发送消息。
    """

    def __init__(self, context: Any, access_control: AccessControl):
        self.context = context
        self.access_control = access_control

    async def push_new_posts(self, posts: list[PostItem], config: dict):
        """推送新消息到所有配置的目标会话"""
        push_groups = set(str(g) for g in config.get("push_groups", []))
        push_privates = set(str(p) for p in config.get("push_privates", []))

        if not push_groups and not push_privates:
            logger.info("未配置推送目标（push_groups / push_privates 均为空）")
            return

        for post in posts:
            message = self._format_message(post)

            # 推送群聊
            for group_id in push_groups:
                if self.access_control.check_group(group_id):
                    try:
                        await self._send_message(group_id=group_id, message=message)
                        logger.info(f"已推送消息到群 {group_id}: {post.title}")
                    except Exception as e:
                        logger.error(f"推送群 {group_id} 失败: {e}")

            # 推送私聊
            for user_id in push_privates:
                if self.access_control.check_private(user_id):
                    try:
                        await self._send_message(user_id=user_id, message=message)
                        logger.info(f"已推送消息到用户 {user_id}: {post.title}")
                    except Exception as e:
                        logger.error(f"推送用户 {user_id} 失败: {e}")

    def _format_message(self, post: PostItem) -> str:
        """格式化推送消息"""
        lines = [
            "【百分之一消息】",
            post.title,
        ]
        if post.summary:
            lines.append("")
            summary = post.summary[:200] + "..." if len(post.summary) > 200 else post.summary
            lines.append(summary)

        if post.url:
            lines.append("")
            lines.append(f"查看详情: {post.url}")

        if post.images:
            lines.append("")
            lines.append(f"图片: {post.images[0]}")
            if len(post.images) > 1:
                lines.append(f"（共 {len(post.images)} 张图片）")

        return "\n".join(lines)

    async def _send_message(self, group_id: str = "", user_id: str = "", message: str = ""):
        """通过 AstrBot 内部 API 发送消息。

        优先使用 context 的 send_message 方法（aiocqhttp 适配器），
        如不可用则尝试通过平台适配器发送。
        """
        try:
            # 方式一：通过 context.send_message（aiocqhttp 适配器标准方法）
            if hasattr(self.context, "send_message"):
                if group_id:
                    await self.context.send_message(
                        "group", group_id, message
                    )
                elif user_id:
                    await self.context.send_message(
                        "private", user_id, message
                    )
                else:
                    logger.warning("send_message: 未指定 group_id 或 user_id")
                return

            # 方式二：通过平台适配器的 send_by_session
            adapter = self._get_platform_adapter()
            if adapter:
                from astrbot.api.message_components import Plain
                from astrbot.api.event import MessageChain
                from astrbot.core.platform.astr_message_event import MessageSesion

                target_id = group_id or user_id
                msg_type = "group" if group_id else "private"
                session = MessageSesion(
                    session_id=target_id,
                    message_type=msg_type,
                )

                chain = MessageChain()
                chain.chain = [Plain(text=message)]
                await adapter.send_by_session(session, chain)
                return

        except Exception as e:
            logger.error(f"AstrBot 消息发送异常: {e}")

        logger.warning(
            f"无法发送消息: context 无 send_message 且无可用平台适配器"
        )

    def _get_platform_adapter(self):
        """获取当前已注册的平台适配器"""
        try:
            # 尝试通过 context 的 platform 属性获取
            if hasattr(self.context, "platform"):
                return self.context.platform
            if hasattr(self.context, "get_platform_adapter"):
                return self.context.get_platform_adapter()
        except Exception as e:
            logger.debug(f"获取平台适配器失败: {e}")
        return None
