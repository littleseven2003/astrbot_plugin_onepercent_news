"""
百分之一消息推送插件 - 主入口

自动同步 TapTap 官方消息（用户"五维互娱"）到 QQ 群聊/私聊。
"""

import asyncio
from pathlib import Path

from astrbot.api import logger  # 使用 AstrBot 内置 logger，确保日志可见
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Plain, Image
from astrbot.api.star import Star, Context

from .crawler.taptap_client import TapTapClient
from .crawler.parser import PostParser
from .cache.post_cache import PostCache
from .filter.access_control import AccessControl
from .handler.query_handler import QueryHandler
from .handler.push_handler import PushHandler

PLUGIN_DIR = Path(__file__).parent
DATA_DIR = PLUGIN_DIR / "data"


class OnePercentNewsPlugin(Star):
    """百分之一消息推送插件"""

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._running = False
        self._crawl_task: asyncio.Task | None = None
        self._initial_crawl_done = False

        # 初始化各模块
        self.tap_client = TapTapClient(
            uid=self.config.get("tap_uid", "19675784"),
            user_agent=self.config.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            ),
            timeout=self.config.get("crawl_timeout", 15),
            retry=self.config.get("crawl_retry", 2),
        )
        self.parser = PostParser()

        db_path = DATA_DIR / "posts.db"
        max_history = self.config.get("max_history", 200)
        self.cache = PostCache(db_path=db_path, max_history=max(max_history, 10))

        access_list_path = DATA_DIR / "access_list.json"
        self.access_control = AccessControl(
            config=self.config,
            access_list_path=access_list_path,
        )

        self.push_handler = PushHandler(context=context, access_control=self.access_control)
        self.query_handler = QueryHandler(
            cache=self.cache,
            access_control=self.access_control,
            config=self.config,
        )

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._running = True

        # 检测旧版本缓存（ordered_content 为空），自动清理并重爬
        stale_count = self.cache.count_stale()
        if stale_count > 0:
            logger.warning(
                f"⚠️ 检测到 {stale_count} 条旧缓存数据（ordered_content 为空）"
            )
            deleted = self.cache.clear_all()
            self._initial_crawl_done = False  # 重置，允许重爬
            logger.info(
                f"🗑️ 已自动清理 {deleted} 条旧缓存，将在首次交互时重新爬取"
            )

        logger.info("百分之一消息推送插件已加载（v0.3.2），等待首次交互触发爬取")

    # ---- 生命周期 ----

    @filter.on_astrbot_loaded()
    async def _on_astrbot_loaded(self):
        """AstrBot 首次启动完全加载后触发爬取"""
        if not self._initial_crawl_done:
            logger.info("AstrBot 加载完成，触发首次爬取")
            await self._do_initial_crawl()

    async def _do_initial_crawl(self):
        """首次爬取 + 启动定时循环。幂等。"""
        if self._initial_crawl_done:
            return
        self._initial_crawl_done = True

        logger.info("🚀 执行首次爬取...")
        try:
            await self._do_crawl()
        except Exception as e:
            logger.error(f"首次爬取异常: {e}", exc_info=True)

        crawl_interval = max(self.config.get("crawl_interval", 300), 60)
        self._crawl_task = asyncio.ensure_future(self._crawl_loop(crawl_interval))
        logger.info(f"后台爬虫已启动，间隔 {crawl_interval}s")

    async def _ensure_crawled(self):
        """确保至少执行过一次爬取。供 on_message 在回复前调用。"""
        if not self._initial_crawl_done:
            await self._do_initial_crawl()

    async def terminate(self):
        self._running = False
        if self._crawl_task:
            self._crawl_task.cancel()
            try:
                await self._crawl_task
            except asyncio.CancelledError:
                pass
        logger.info("百分之一消息推送插件已停止")

    async def _crawl_loop(self, interval: int):
        while self._running:
            try:
                await self._do_crawl()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"定时爬取异常: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _do_crawl(self):
        logger.info("🔍 请求 TapTap API...")
        try:
            raw_data = await self.tap_client.fetch_user_moments()
            posts = self.parser.parse(raw_data)
            fetched = len(posts)

            new_posts = []
            for post in posts:
                if self.cache.is_new(post.post_id):
                    new_posts.append(post)

            # 对新增帖子，获取详情并填充 ordered_content
            for post in new_posts:
                await self._enrich_ordered_content(post)
                await asyncio.sleep(0.5)  # 避免详情 API 限流

            for post in new_posts:
                self.cache.mark_pushed(post)

            total = len(self.cache.get_recent_posts(
                self.config.get("max_history", 200)
            ))

            if new_posts:
                logger.info(
                    f"📥 爬取完成：获取 {fetched} 条，新增 {len(new_posts)} 条，"
                    f"缓存共 {total} 条"
                )
                await self.push_handler.push_new_posts(new_posts, self.config)
            else:
                logger.info(
                    f"📥 爬取完成：获取 {fetched} 条，无新增，缓存共 {total} 条"
                )

            self.cache.prune_old_posts()
        except Exception as e:
            logger.error(f"❌ 爬取失败: {e}", exc_info=True)

    async def _enrich_ordered_content(self, post):
        """调用帖子详情 API → 解析 HTML 原文 → 填充 ordered_content"""
        from .crawler.parser import PostParser

        # 策略一：详情 API 获取完整 HTML 原文
        if post.topic_id:
            detail = await self.tap_client.fetch_post_detail(post.topic_id)
            if detail:
                fp = detail.get("first_post", {})
                contents = fp.get("contents", {})
                html_text = contents.get("text", "")
                if html_text:
                    post.ordered_content = PostParser.parse_ordered_content(html_text)
                    texts = sum(1 for s in post.ordered_content if s["type"] == "text")
                    imgs = sum(1 for s in post.ordered_content if s["type"] == "image")
                    logger.info(
                        f"  📝 {post.title[:20]}... "
                        f"详情API: {len(post.ordered_content)} 段 ({texts}文{imgs}图)"
                    )
                    return
            logger.debug(f"  ⚠️ {post.title[:20]}... 详情API无数据，尝试 summary fallback")

        # 策略二：fallback → 用 summary（同样是 HTML，含 <img> 标签）
        if post.summary:
            post.ordered_content = PostParser.parse_ordered_content(post.summary)
            texts = sum(1 for s in post.ordered_content if s["type"] == "text")
            imgs = sum(1 for s in post.ordered_content if s["type"] == "image")
            logger.warning(
                f"  ⚠️ {post.title[:20]}... summary fallback: "
                f"{len(post.ordered_content)} 段 ({texts}文{imgs}图)"
            )
            return

        # 策略三：最后兜底 → 纯文本 + 所有图片
        ordered = []
        if post.summary:
            ordered.append({"type": "text", "text": post.summary})
        for img_url in post.images:
            ordered.append({"type": "image", "url": img_url})
        post.ordered_content = ordered
        logger.warning(
            f"  ❌ {post.title[:20]}... 最终兜底: "
            f"images 全部追加到末尾 (共 {len(post.images)} 张)"
        )

    # ------- 命令 -------

    @filter.command("清除百分之一消息缓存")
    async def clear_history(self, event: AstrMessageEvent):
        """清空所有缓存数据并重置爬取状态"""
        deleted = self.cache.clear_all()
        self._initial_crawl_done = False  # 重置，允许下次查询重爬
        if deleted > 0:
            logger.info(f"🗑️ 用户 {event.get_sender_name()} 触发了清除缓存，删除了 {deleted} 条记录，已重置爬取状态")
            yield event.plain_result(f"✅ 已清空 {deleted} 条缓存，下次查询时将重新爬取最新数据。")
        else:
            logger.info(f"🗑️ 用户 {event.get_sender_name()} 触发清除缓存，但缓存为空")
            yield event.plain_result("缓存为空，无需清理。")

    # ------- 消息 Handler -------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if not self._running:
            return

        message = event.message_str.strip() if hasattr(event, "message_str") else ""
        if not message:
            return

        user_id = str(event.get_sender_id()) if hasattr(event, "get_sender_id") else ""
        session_id = str(event.get_session_id()) if hasattr(event, "get_session_id") else ""
        group_id = str(event.get_group_id()) if (hasattr(event, "get_group_id") and event.get_group_id()) else ""

        # 序号交互（纯数字）
        if message.isdigit():
            index = int(message)
            handled, reply_text, ordered_content = self.query_handler.handle_index_reply(
                user_id=user_id, session_id=session_id, index=index,
            )
            if handled:
                if reply_text:
                    chain = [Plain(text=reply_text)]
                    for seg in ordered_content:
                        if seg.get("type") == "text":
                            chain.append(Plain(text=seg["text"]))
                        elif seg.get("type") == "image":
                            chain.append(Image(seg["url"]))
                    yield event.chain_result(chain)
                event.stop_event()
            return

        # 关键词触发
        keywords = self.config.get(
            "trigger_keywords",
            ["五维消息", "百分之一消息", "五维通知", "百分之一通知"],
        )
        if message in keywords:
            # 在回复前同步等待爬取完成，确保用户看到的不是"暂无消息"
            await self._ensure_crawled()

            handled, reply_text = self.query_handler.handle_keyword_trigger(
                user_id=user_id, session_id=session_id, group_id=group_id,
            )
            if handled:
                if reply_text:
                    yield event.plain_result(reply_text)
                event.stop_event()
