"""消息处理模块 - 自动推送新消息"""

from typing import Any

from astrbot.api import logger

from ..crawler.parser import PostItem
from ..crawler.image_renderer import render_post_to_image
from ..crawler.page_screenshot import capture_posts_screenshot_batch
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

        if mode != "detail":
            return

        display_mode = config.get("detail_display_mode", "text_image")

        if display_mode == "playwright":
            await self._push_detail_playwright(posts, groups, privates)
        elif display_mode == "pillow":
            await self._push_detail_pillow(posts, groups, privates)
        else:
            await self._push_detail_text_image(posts, groups, privates)

        logger.info(
            f"已推送 {len(posts)} 条新消息到 {len(groups)} 个群 "
            f"+ {len(privates)} 个用户 (mode={mode}, display={display_mode})"
        )

    # ---------- 详情推送：图文混排 ----------

    async def _push_detail_text_image(
        self, posts: list[PostItem], groups: list[str], privates: list[str]
    ):
        for post in posts:
            chain = self._build_post_chain(post)
            for target_id in groups:
                try:
                    await self._send_chain(group_id=target_id, chain=chain)
                except Exception as e:
                    logger.error(f"推送群 {target_id} 详情失败: {e}")
            for target_id in privates:
                try:
                    await self._send_chain(user_id=target_id, chain=chain)
                except Exception as e:
                    logger.error(f"推送用户 {target_id} 详情失败: {e}")

    # ---------- 详情推送：Playwright 批量截图 ----------

    async def _push_detail_playwright(
        self, posts: list[PostItem], groups: list[str], privates: list[str]
    ):
        from ..crawler.page_screenshot import screenshot_session

        post_ids = [p.post_id for p in posts if p.post_id]
        if not post_ids:
            logger.warning("无有效 post_id，回退到图文模式")
            await self._push_detail_text_image(posts, groups, privates)
            return

        logger.info(f"开始 Playwright 截图推送: {len(post_ids)} 帖")
        post_map = {p.post_id: p for p in posts}

        try:
            async with screenshot_session() as screenshot:
                for pid in post_ids:
                    buf = await screenshot(pid)
                    if buf:
                        await self._send_image(buf, post_map[pid].title, groups, privates)
                    else:
                        post = post_map[pid]
                        logger.warning(f"截图失败，回退图文: {post.title[:20]}")
                        chain = self._build_post_chain(post)
                        for target_id in groups:
                            try:
                                await self._send_chain(group_id=target_id, chain=chain)
                            except Exception as e:
                                logger.error(f"推送群 {target_id} 失败: {e}")
                        for target_id in privates:
                            try:
                                await self._send_chain(user_id=target_id, chain=chain)
                            except Exception as e:
                                logger.error(f"推送用户 {target_id} 失败: {e}")
        except Exception as e:
            logger.error(f"Playwright 截图会话异常: {e}", exc_info=True)
            await self._push_detail_text_image(posts, groups, privates)

    # ---------- 详情推送：Pillow 逐帖渲染 ----------

    async def _push_detail_pillow(
        self, posts: list[PostItem], groups: list[str], privates: list[str]
    ):
        for post in posts:
            try:
                buf = await render_post_to_image(post)
            except Exception as e:
                logger.warning(f"Pillow 渲染失败: {post.title[:20]}: {e}")
                buf = None

            if buf:
                await self._send_image(buf, post.title, groups, privates)
            else:
                logger.warning(f"Pillow 渲染失败，回退图文: {post.title[:20]}")
                chain = self._build_post_chain(post)
                for target_id in groups:
                    try:
                        await self._send_chain(group_id=target_id, chain=chain)
                    except Exception as e:
                        logger.error(f"推送群 {target_id} 详情失败: {e}")
                for target_id in privates:
                    try:
                        await self._send_chain(user_id=target_id, chain=chain)
                    except Exception as e:
                        logger.error(f"推送用户 {target_id} 详情失败: {e}")

    # ---------- 发送图片 ----------

    async def _send_image(
        self, buf, title: str, groups: list[str], privates: list[str]
    ):
        """将 BytesIO 写临时文件后发送为图片消息。"""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Image as ImageComponent

        temp_path = write_temp_image(buf)
        chain = MessageChain()
        chain.chain = [ImageComponent(temp_path)]

        for target_id in groups:
            try:
                await self._send_chain(group_id=target_id, chain=chain)
            except Exception as e:
                logger.error(f"推送群 {target_id} 图片失败: {e}")
        for target_id in privates:
            try:
                await self._send_chain(user_id=target_id, chain=chain)
            except Exception as e:
                logger.error(f"推送用户 {target_id} 图片失败: {e}")

    # ---------- 辅助 ----------

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

    @staticmethod
    def _build_post_chain(post: PostItem):
        """构造图文混排 MessageChain。"""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain, Image

        chain = MessageChain()
        parts = []

        header = f"【{post.title}】\n\n发布时间: {post.published_at}"
        if post.url:
            header += f"\n原帖链接: {post.url}"
        parts.append(Plain(text=header))

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

    # ---------- 发送通道 ----------

    async def _send_text(
        self, group_id: str = "", user_id: str = "", text: str = ""
    ):
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

        if hasattr(self.context, "send_message"):
            try:
                ok = await self.context.send_message(session_str, chain)
                if ok:
                    return
                logger.warning(f"[推送] ❌ send_message 返回 False: {session_str}")
            except Exception as e:
                logger.warning(f"[推送] send_message 异常: {e}")

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
        try:
            for plat in self.context.platform_manager.platform_insts:
                if plat.meta().name == "aiocqhttp":
                    pid = plat.meta().id
                    return pid
            logger.warning("[推送] ⚠️ 未找到 aiocqhttp 平台适配器")
        except Exception as e:
            logger.warning(f"[推送] 获取 platform_id 失败: {e}")
        return ""
