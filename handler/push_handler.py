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

        text = self._format_push_list(posts, config)

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
    def _format_push_list(posts: list[PostItem], config: dict) -> str:
        lines = ["【百分之一 · 新消息】", ""]
        for i, post in enumerate(posts, 1):
            img_tag = f" ({len(post.images)}图)" if post.images else ""
            lines.append(f"🆕 {i}. {post.title}{img_tag}")

        lines.append("")
        # 从配置中读取触发关键词，展示为 "发送 XX/XX/XX 查看完整列表与详情"
        keywords = config.get(
            "trigger_keywords",
            ["五维消息", "百分之一消息", "五维通知", "百分之一通知"],
        )
        kw_display = " / ".join(keywords)
        lines.append(f"发送 {kw_display} 查看完整列表与详情")
        return "\n".join(lines)

    # ---------- sending ----------

    async def _send_text(
        self, group_id: str = "", user_id: str = "", text: str = ""
    ):
        """通过平台适配器直接发送纯文本（绕过 send_message 字符串解析）。"""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain
        from astrbot.core.platform.astr_message_event import MessageSesion

        target_id = group_id or user_id
        chain = MessageChain()
        chain.chain = [Plain(text=text)]
        msg_type = "group" if group_id else "private"

        try:
            pm = self.context.platform_manager
            for platform in pm.platform_insts:
                session = MessageSesion(
                    platform_name=platform.meta().id,
                    session_id=target_id,
                    message_type=msg_type,
                )
                try:
                    await platform.send_by_session(session, chain)
                    return
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"适配器发送失败: {e}")

        logger.warning(f"无法发送消息到 {target_id}")
