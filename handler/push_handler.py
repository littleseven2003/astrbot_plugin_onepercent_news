"""消息处理模块 - 自动推送新消息"""

import logging
from typing import Any

from ..crawler.parser import PostItem
from ..filter.access_control import AccessControl

logger = logging.getLogger(__name__)


class PushHandler:
    """将新消息推送到配置的目标群聊/私聊"""

    def __init__(self, context: Any, access_control: AccessControl):
        self.context = context
        self.access_control = access_control

    async def push_new_posts(self, posts: list[PostItem], config: dict):
        """推送新消息到所有配置的目标会话"""
        push_groups = set(str(g) for g in config.get("push_groups", []))
        push_privates = set(str(p) for p in config.get("push_privates", []))

        for post in posts:
            message = self._format_message(post)

            # 推送群聊
            for group_id in push_groups:
                if self.access_control.check_group(group_id):
                    try:
                        await self._send_group(group_id, message)
                        logger.info(f"已推送消息到群 {group_id}: {post.title}")
                    except Exception as e:
                        logger.error(f"推送群 {group_id} 失败: {e}")

            # 推送私聊
            for user_id in push_privates:
                if self.access_control.check_private(user_id):
                    try:
                        await self._send_private(user_id, message)
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
            # 只推送第一张图片 URL，其余以链接形式
            lines.append(f"图片: {post.images[0]}")
            if len(post.images) > 1:
                lines.append(f"（共 {len(post.images)} 张图片）")

        return "\n".join(lines)

    async def _send_group(self, group_id: str, message: str):
        """发送群聊消息"""
        try:
            # 使用 AstrBot 的 context 发送消息
            if hasattr(self.context, "send_group_msg"):
                await self.context.send_group_msg(group_id=group_id, message=message)
            elif hasattr(self.context, "send_message"):
                await self.context.send_message(
                    message_type="group", session_id=group_id, message=message
                )
            else:
                logger.warning(f"无法发送群聊消息: 未找到可用的发送方法")
        except Exception as e:
            logger.error(f"发送群聊消息失败: {e}")

    async def _send_private(self, user_id: str, message: str):
        """发送私聊消息"""
        try:
            if hasattr(self.context, "send_private_msg"):
                await self.context.send_private_msg(user_id=user_id, message=message)
            elif hasattr(self.context, "send_message"):
                await self.context.send_message(
                    message_type="private", session_id=user_id, message=message
                )
            else:
                logger.warning(f"无法发送私聊消息: 未找到可用的发送方法")
        except Exception as e:
            logger.error(f"发送私聊消息失败: {e}")
