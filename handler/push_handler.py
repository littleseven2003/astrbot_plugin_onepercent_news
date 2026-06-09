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
        """推送新消息列表到所有被允许的群聊/私聊。"""
        groups, privates = self.access_control.get_push_targets()

        if not groups and not privates:
            logger.info("无推送目标（黑名单模式无法枚举全部，请使用白名单）")
            return

        text = self._format_push_list(posts, config)

        for group_id in groups:
            try:
                await self._send_text(group_id=group_id, text=text)
                logger.info(
                    f"已推送 {len(posts)} 条新消息标题到群 {group_id}"
                )
            except Exception as e:
                logger.error(f"推送群 {group_id} 失败: {e}")

        for user_id in privates:
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
        """发送纯文本消息 — 试 send_message 再 adapter 兜底。"""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain

        target_id = group_id or user_id
        chain = MessageChain()
        chain.chain = [Plain(text=text)]

        pid = self._get_platform_id()
        if not pid:
            logger.warning(f"[推送] 无法获取 platform_id，跳过发送")
            return

        session_str = (
            f"{pid}:GroupMessage:{target_id}" if group_id
            else f"{pid}:FriendMessage:{target_id}"
        )

        # 方式一：context.send_message
        if hasattr(self.context, "send_message"):
            try:
                ok = await self.context.send_message(session_str, chain)
                if ok:
                    logger.info(f"[推送] ✅ send_message 成功: {session_str}")
                    return
                logger.warning(f"[推送] ❌ send_message 返回 False: {session_str}")
            except Exception as e:
                logger.warning(f"[推送] send_message 异常: {e}")

        # 方式二：adapter 直发
        try:
            from astrbot.core.platform.astr_message_event import MessageSesion
            from astrbot.core.platform.message_type import MessageType
            pm = self.context.platform_manager
            for plat in pm.platform_insts:
                if plat.meta().id == pid:
                    session = MessageSesion(
                        platform_name=pid,
                        message_type=MessageType.GROUP_MESSAGE if group_id else MessageType.FRIEND_MESSAGE,
                        session_id=target_id,
                    )
                    await plat.send_by_session(session, chain)
                    logger.info(f"[推送] ✅ adapter.send_by_session 成功: {pid}")
                    return
        except Exception as e:
            logger.warning(f"[推送] adapter 发送异常: {type(e).__name__}: {e}")

        logger.warning(f"[推送] ❌ 所有方式均失败: {target_id}")

    def _get_platform_id(self) -> str:
        """获取 aiocqhttp 平台适配器的 meta().id"""
        try:
            for plat in self.context.platform_manager.platform_insts:
                if plat.meta().name == "aiocqhttp":
                    pid = plat.meta().id
                    logger.info(f"[推送] 找到 QQ 平台: id={pid}, name={plat.meta().name}")
                    return pid
            logger.warning("[推送] ⚠️ 未找到 aiocqhttp 平台适配器")
        except Exception as e:
            logger.warning(f"[推送] 获取 platform_id 失败: {e}")
        return ""
