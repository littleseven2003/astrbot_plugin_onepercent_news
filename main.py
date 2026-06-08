"""
百分之一消息推送插件 - 主入口

自动同步 TapTap 官方消息（用户"五维互娱"）到 QQ 群聊/私聊。

AstrBot v4.25.5 兼容注意：
- __init__ 中用 loop.call_later 延迟调度爬虫（事件循环就绪后才能执行）
- on_astrbot_loaded 作为补充触发（首次启动时）
- on_message 首次交互作为兜底触发（热重载场景）
"""

import asyncio
import logging
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Star, Context

from .crawler.taptap_client import TapTapClient
from .crawler.parser import PostParser
from .cache.post_cache import PostCache
from .filter.access_control import AccessControl
from .handler.query_handler import QueryHandler
from .handler.push_handler import PushHandler

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).parent
DATA_DIR = PLUGIN_DIR / "data"


class OnePercentNewsPlugin(Star):
    """百分之一消息推送插件"""

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._running = False
        self._crawl_task: asyncio.Task | None = None
        self._initial_crawl_done = False  # 首次爬取是否已完成

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

        # 确保 data 目录存在
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # 立即设置运行标志（消息处理器可工作）
        self._running = True

        # ---- 延迟调度首次爬取 ----
        # asyncio.ensure_future() 在 __init__ 同步上下文中不可靠，
        # 改用 loop.call_later 将爬取任务注册到事件循环，延迟执行。
        try:
            loop = asyncio.get_event_loop()
            loop.call_later(5, self._trigger_initial_crawl_via_loop)
            logger.info("📋 百分之一消息推送插件已初始化，首次爬取将在 5 秒后开始")
        except Exception as e:
            logger.warning(f"无法通过事件循环调度爬虫（将在首次交互时触发）: {e}")

    # ---------- 生命周期 ----------

    def _trigger_initial_crawl_via_loop(self):
        """通过事件循环回调触发首次爬取（call_later 回调是同步的，需要再次调度异步任务）"""
        if self._initial_crawl_done:
            return
        asyncio.ensure_future(self._do_initial_crawl())

    @filter.on_astrbot_loaded()
    async def _on_astrbot_loaded(self):
        """AstrBot 首次启动完全加载后触发爬取（补充保障）"""
        if not self._initial_crawl_done:
            logger.info("🔔 AstrBot 加载完成，触发首次爬取")
            await self._do_initial_crawl()

    async def _do_initial_crawl(self):
        """执行首次爬取并启动后台定时循环。幂等：只执行一次。"""
        if self._initial_crawl_done:
            return
        self._initial_crawl_done = True

        logger.info("🚀 开始首次爬取...")
        try:
            await self._do_crawl()
        except Exception as e:
            logger.error(f"首次爬取异常: {e}", exc_info=True)

        # 启动后台定时爬取循环
        crawl_interval = max(self.config.get("crawl_interval", 300), 60)
        self._crawl_task = asyncio.ensure_future(self._crawl_loop(crawl_interval))
        logger.info(f"✅ 后台爬虫已启动，定时间隔: {crawl_interval}s")

    async def terminate(self):
        """插件停止"""
        self._running = False
        if self._crawl_task:
            self._crawl_task.cancel()
            try:
                await self._crawl_task
            except asyncio.CancelledError:
                pass
        logger.info("百分之一消息推送插件已停止")

    async def _crawl_loop(self, interval: int):
        """后台定时爬取循环"""
        while self._running:
            try:
                await self._do_crawl()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"爬取循环异常: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _do_crawl(self):
        """执行一次爬取并推送新消息"""
        logger.info("🔍 开始爬取 TapTap 动态...")
        try:
            raw_data = await self.tap_client.fetch_user_moments()
            posts = self.parser.parse(raw_data)
            fetched_count = len(posts)

            # 去重：分离新帖子
            new_posts = []
            for post in posts:
                if self.cache.is_new(post.post_id):
                    new_posts.append(post)

            # 写入缓存
            for post in new_posts:
                self.cache.mark_pushed(post)

            # 获取缓存总数
            total_count = len(self.cache.get_recent_posts(
                self.config.get("max_history", 200)
            ))

            if new_posts:
                logger.info(
                    f"📥 爬取结果: 本次获取 {fetched_count} 条，"
                    f"新增 {len(new_posts)} 条，当前共 {total_count} 条"
                )
                await self.push_handler.push_new_posts(new_posts, self.config)
            else:
                logger.info(
                    f"📥 爬取结果: 本次获取 {fetched_count} 条，"
                    f"无新消息，当前共 {total_count} 条"
                )

            # 清理旧数据
            self.cache.prune_old_posts()
        except Exception as e:
            logger.error(f"❌ 爬取失败: {e}", exc_info=True)

    # ------- 消息 Handler -------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理所有消息事件"""
        if not self._running:
            return

        # 兜底：首次爬取还没完成，立即异步触发（不阻塞当前消息处理）
        if not self._initial_crawl_done:
            asyncio.ensure_future(self._do_initial_crawl())

        message = event.message_str.strip() if hasattr(event, "message_str") else ""
        if not message:
            return

        # 获取会话信息
        user_id = str(event.get_sender_id()) if hasattr(event, "get_sender_id") else ""
        session_id = str(event.get_session_id()) if hasattr(event, "get_session_id") else ""
        is_group = hasattr(event, "get_group_id") and event.get_group_id()

        group_id = str(event.get_group_id()) if is_group else ""

        # 序号交互（纯数字）
        if message.isdigit():
            index = int(message)
            handled, reply_text = self.query_handler.handle_index_reply(
                user_id=user_id,
                session_id=session_id,
                index=index,
            )
            if handled:
                if reply_text:
                    yield event.plain_result(reply_text)
                event.stop_event()
            return

        # 关键词触发
        keywords = self.config.get(
            "trigger_keywords",
            ["五维消息", "百分之一消息", "五维通知", "百分之一通知"],
        )
        if message in keywords:
            handled, reply_text = self.query_handler.handle_keyword_trigger(
                user_id=user_id,
                session_id=session_id,
                group_id=group_id,
            )
            if handled:
                if reply_text:
                    yield event.plain_result(reply_text)
                event.stop_event()
