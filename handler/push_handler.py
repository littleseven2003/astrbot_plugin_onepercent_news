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
        """推送新消息到所有被允许的群聊/私聊。"""
        groups, privates = self.access_control.get_push_targets()

        if not groups and not privates:
            logger.info("无推送目标（黑名单模式无法枚举全部，请使用白名单）")
            return

        mode = config.get("push_mode", "list")

        # 先发消息列表作为摘要（底部有查看详情提示）
        list_text = self._format_push_list(posts, config)
        for group_id in groups:
            try:
                await self._send_text(group_id=group_id, text=list_text)
            except Exception as e:
                logger.error(f"推送群 {group_id} 列表失败: {e}")
        for user_id in privates:
            try:
                await self._send_text(user_id=user_id, text=list_text)
            except Exception as e:
                logger.error(f"推送用户 {user_id} 列表失败: {e}")

        # 详情模式：逐条展开（文本 + 图片）
        if mode == "detail":
            for post in posts:
                # 先发送文本详情
                detail_text = self._format_post_detail_text(post)
                for target_groups, target_privates, send_fn in [
                    (groups, privates, self._send_text)
                ]:
                    for group_id in groups:
                        try:
                            await self._send_text(group_id=group_id, text=detail_text)
                        except Exception as e:
                            logger.error(f"推送群 {group_id} 文本失败: {e}")
                    for user_id in privates:
                        try:
                            await self._send_text(user_id=user_id, text=detail_text)
                        except Exception as e:
                            logger.error(f"推送用户 {user_id} 文本失败: {e}")

                # 发送图片（从 ordered_content 或 images 提取）
                images = post.images
                if post.ordered_content:
                    images = [
                        seg["url"] for seg in post.ordered_content
                        if seg.get("type") == "image"
                    ]
                for img_url in images:
                    for group_id in groups:
                        try:
                            await self._send_image(group_id=group_id, url=img_url)
                        except Exception as e:
                            logger.error(f"推送群 {group_id} 图片失败: {e}")
                    for user_id in privates:
                        try:
                            await self._send_image(user_id=user_id, url=img_url)
                        except Exception as e:
                            logger.error(f"推送用户 {user_id} 图片失败: {e}")

        logger.info(
            f"已推送 {len(posts)} 条新消息到 {len(groups)} 个群 + {len(privates)} 个用户 "
            f"(mode={mode})"
        )

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

    @staticmethod
    def _format_post_detail_text(post: PostItem) -> str:
        """格式化单条帖子详情文本（不含图片，图片由 _send_image 发送）。"""
        lines = [f"【{post.title}】"]
        lines.append(f"发布时间: {post.published_at}")
        if post.url:
            lines.append(f"原帖链接: {post.url}")
        lines.append("")

        if post.ordered_content:
            for seg in post.ordered_content:
                if seg.get("type") == "text":
                    lines.append(seg["text"])
                elif seg.get("type") == "image":
                    lines.append(seg["url"])
        elif post.summary:
            lines.append(post.summary)
            if post.images:
                for img in post.images:
                    lines.append(f"[图片: {img}]")

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

    async def _send_image(
        self, group_id: str = "", user_id: str = "", url: str = ""
    ):
        """发送图片消息 — 与 _send_text 相同的发送通道，但用 Image 组件。"""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Image

        target_id = group_id or user_id
        chain = MessageChain()
        chain.chain = [Image(url)]

        pid = self._get_platform_id()
        if not pid:
            return

        session_str = (
            f"{pid}:GroupMessage:{target_id}" if group_id
            else f"{pid}:FriendMessage:{target_id}"
        )

        if hasattr(self.context, "send_message"):
            try:
                await self.context.send_message(session_str, chain)
                return
            except Exception:
                pass

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
                    return
        except Exception:
            pass

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
