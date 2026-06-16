"""消息处理模块 - 自动推送新消息"""

from typing import Any

from astrbot.api import logger

from ..crawler.parser import PostItem
from ..crawler.image_renderer import render_post_to_image
from ..crawler.page_screenshot import capture_post_screenshot
from ..crawler import write_temp_image
from ..filter.access_control import AccessControl


class PushHandler:
    """新消息推送：向目标发送标题列表，或逐帖详情。"""

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

        # 详情模式：每个帖子一条 MessageChain
        # Plain 文字 + Image 图片按 ordered_content 顺序混排
        if mode == "detail":
            display_mode = config.get("detail_display_mode", "text_image")
            for post in posts:
                if display_mode == "image":
                    # 图片消息模式：将整个帖子渲染为图片
                    await self._send_post_as_image(post, groups, privates)
                else:
                    # 图文消息模式：使用原有的图文混排方式
                    chain = self._build_post_chain(post)
                    for group_id in groups:
                        try:
                            await self._send_chain(group_id=group_id, chain=chain)
                        except Exception as e:
                            logger.error(f"推送群 {group_id} 详情失败: {e}")
                    for user_id in privates:
                        try:
                            await self._send_chain(user_id=user_id, chain=chain)
                        except Exception as e:
                            logger.error(f"推送用户 {user_id} 详情失败: {e}")

        logger.info(
            f"已推送 {len(posts)} 条新消息到 {len(groups)} 个群 "
            f"+ {len(privates)} 个用户 (mode={mode})"
        )

    @staticmethod
    def _format_push_list(posts: list[PostItem], config: dict) -> str:
        lines = ["【百分之一 · 新消息】", ""]
        for i, post in enumerate(posts, 1):
            img_tag = f" ({len(post.images)}图)" if post.images else ""
            lines.append(f"🆕 {i}. {post.title}{img_tag}")

        lines.append("")
        keywords = config.get(
            "trigger_keywords",
            ["五维消息", "百分之一消息", "五维通知", "百分之一通知"],
        )
        kw_display = " / ".join(keywords)
        lines.append(f"发送 {kw_display} 查看完整列表与详情")
        return "\n".join(lines)

    # ---------- 单帖详情链条构造 ----------

    @staticmethod
    def _build_post_chain(post: PostItem):
        """构造与序号回复详情完全一致的 MessageChain。"""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain, Image

        chain = MessageChain()
        parts = []

        # 头部（与 query_handler.handle_index_reply 一致）
        header = f"【{post.title}】\n\n发布时间: {post.published_at}"
        if post.url:
            header += f"\n原帖链接: {post.url}"
        parts.append(Plain(text=header))

        # 有序内容
        if post.ordered_content:
            for seg in post.ordered_content:
                if seg.get("type") == "text":
                    parts.append(Plain(text=seg["text"]))
                elif seg.get("type") == "image":
                    parts.append(Image(seg["url"]))
        elif post.images:
            for img_url in post.images:
                parts.append(Image(img_url))

        chain.chain = parts
        return chain

    # ---------- 图片消息发送 ----------

    async def _send_post_as_image(self, post: PostItem, groups: list[str], privates: list[str]):
        """将帖子渲染为图片并发送

        优先使用页面截图，如果失败则回退到 Pillow 自绘。
        """
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Image as ImageComponent

        image_buf = None

        # 方式一：页面截图（优先）
        if post.post_id:
            try:
                image_buf = await capture_post_screenshot(post.post_id)
                if image_buf:
                    logger.info(f"✅ 页面截图成功: {post.title[:20]}...")
            except Exception as e:
                logger.warning(f"页面截图失败 {post.post_id}: {e}")

        # 方式二：Pillow 自绘（回退）
        if not image_buf:
            try:
                image_buf = await render_post_to_image(post)
                if image_buf:
                    logger.info(f"✅ Pillow 渲染成功: {post.title[:20]}...")
            except Exception as e:
                logger.warning(f"Pillow 渲染失败: {e}")

        # 方式三：回退到图文模式
        if not image_buf:
            logger.warning(f"所有图片渲染方式均失败，回退到图文模式: {post.title[:20]}...")
            chain = self._build_post_chain(post)
            for group_id in groups:
                try:
                    await self._send_chain(group_id=group_id, chain=chain)
                except Exception as e:
                    logger.error(f"推送群 {group_id} 详情失败: {e}")
            for user_id in privates:
                try:
                    await self._send_chain(user_id=user_id, chain=chain)
                except Exception as e:
                    logger.error(f"推送用户 {user_id} 详情失败: {e}")
            return

        # 构造图片消息链
        chain = MessageChain()
        # 将 BytesIO 转换为 base64 或直接使用
        # AstrBot 的 Image 组件支持 BytesIO 对象
        chain.chain = [ImageComponent(write_temp_image(image_buf))]

        # 发送图片消息
        for group_id in groups:
            try:
                await self._send_chain(group_id=group_id, chain=chain)
            except Exception as e:
                logger.error(f"推送群 {group_id} 图片消息失败: {e}")
        for user_id in privates:
            try:
                await self._send_chain(user_id=user_id, chain=chain)
            except Exception as e:
                logger.error(f"推送用户 {user_id} 图片消息失败: {e}")

    # ---------- 发送通道 ----------

    async def _send_text(
        self, group_id: str = "", user_id: str = "", text: str = ""
    ):
        """发送纯文本消息。"""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain

        chain = MessageChain()
        chain.chain = [Plain(text=text)]
        await self._send_chain(group_id=group_id, user_id=user_id, chain=chain)

    async def _send_chain(
        self,
        group_id: str = "",
        user_id: str = "",
        chain=None,
    ):
        """发送 MessageChain — 试 send_message 再 adapter 兜底。"""
        from astrbot.api.event import MessageChain

        if chain is None:
            return

        target_id = group_id or user_id
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
                    return pid
            logger.warning("[推送] ⚠️ 未找到 aiocqhttp 平台适配器")
        except Exception as e:
            logger.warning(f"[推送] 获取 platform_id 失败: {e}")
        return ""
