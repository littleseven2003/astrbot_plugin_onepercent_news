"""
百分之一消息推送插件 - 主入口

自动同步 TapTap 官方消息（用户"五维互娱"）到 QQ 群聊/私聊。
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

        # 设置运行标志（消息处理器一加载即可用）
        self._running = True
        logger.info("百分之一消息推送插件已初始化（爬虫稍后由 on_astrbot_loaded 启动）")

    # ---- 生命周期 ----

    @filter.on_astrbot_loaded()
    async def _on_astrbot_loaded(self):
        """AstrBot 完全加载后启动后台爬虫。
        
        使用 on_astrbot_loaded 钩子而非 __init__ 中启动，
        是因为 AstrBot 事件循环在 __init__ 阶段可能尚未就绪。
        """
        crawl_interval = max(self.config.get("crawl_interval", 300), 60)
        logger.info(f"🚀 启动后台爬虫，间隔: {crawl_interval}s")
        
        # 立即执行首次爬取
        try:
            await self._do_crawl()
        except Exception as e:
            logger.error(f"首次爬取失败: {e}", exc_info=True)
        
        # 启动定时循环
        self._crawl_task = asyncio.ensure_future(self._crawl_loop(crawl_interval))
        logger.info("✅ 后台爬虫已启动")

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
        logger.info("开始爬取 TapTap 动态...")
        try:
            raw_data = await self.tap_client.fetch_user_moments()
            posts = self.parser.parse(raw_data)

            new_posts = []
            for post in posts:
                if self.cache.is_new(post.post_id):
                    new_posts.append(post)

            if new_posts:
                logger.info(f"发现 {len(new_posts)} 条新消息")
                for post in new_posts:
                    self.cache.mark_pushed(post)
                await self.push_handler.push_new_posts(new_posts, self.config)
            else:
                logger.info("无新消息")

            # 清理旧数据
            self.cache.prune_old_posts()
        except Exception as e:
            logger.error(f"爬取失败: {e}", exc_info=True)

    # ------- 消息 Handler -------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理所有消息事件"""
        if not self._running:
            return

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
