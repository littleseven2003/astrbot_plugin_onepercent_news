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

    # ---------- sending ----------

    async def _send_text(
        self, group_id: str = "", user_id: str = "", text: str = ""
    ):
        """通过平台适配器发送纯文本消息。

        优先使用 Context.send_message（需构造 unified_msg_origin 格式），
        失败则通过平台适配器 send_by_session。
        """
        target_id = group_id or user_id

        # 方式一：通过 context.send_message，需 session 格式
        if hasattr(self.context, "send_message"):
            try:
                session_str = self._build_session(group_id, user_id)
                if session_str:
                    await self.context.send_message(session_str, text)
                    return
            except Exception as e:
                logger.debug(f"context.send_message 失败: {e}")

        # 方式二：平台适配器
        adapter = self._get_adapter()
        if adapter:
            from astrbot.api.event import MessageChain
            from astrbot.api.message_components import Plain
            from astrbot.core.platform.astr_message_event import MessageSesion

            chain = MessageChain()
            chain.chain = [Plain(text=text)]
            msg_type = "group" if group_id else "private"
            session = MessageSesion(
                session_id=target_id, message_type=msg_type,
            )
            await adapter.send_by_session(session, chain)
            return

        logger.warning(f"无法发送消息到 {target_id}（无可用适配器）")

    def _build_session(self, group_id: str, user_id: str) -> str:
        """构造 AstrBot unified_msg_origin 格式: platform:type:session_id"""
        meta = self._get_platform_meta()
        if not meta:
            return ""
        platform_id = meta.name  # e.g. "aiocqhttp"
        if group_id:
            return f"{platform_id}:group:{group_id}"
        return f"{platform_id}:friend:{user_id}"

    def _get_platform_meta(self):
        """获取平台元数据（含 name/id）"""
        adapter = self._get_adapter()
        if adapter and hasattr(adapter, "meta"):
            return adapter.meta()
        return None

    def _get_adapter(self):
        try:
            if hasattr(self.context, "platform"):
                return self.context.platform
            if hasattr(self.context, "get_platform_adapter"):
                return self.context.get_platform_adapter()
        except Exception:
            pass
        return None
