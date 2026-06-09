# 更新日志

## v0.4.0 - 2026-06-09

### 新增

- **管理员权限控制**：`/清除百分之一消息缓存` 命令仅管理员可用
  - 新增 `admin_qq` 配置项：管理员 QQ 号列表
  - 非管理员执行清除命令时提示"权限不足"

### 调整

- `_conf_schema.json`：删除 `clear_history` 文本说明，新增 `admin_qq` 列表配置

---

## v0.3.0 - 2026-06-09

### 修复

- **自动推送失败**：`Context.send_message` 参数数量错误（传了 3 个参数，实际签名为 2 个）
  - 改为 `send_message(target_id, text)` 纯文本发送
- **自动推送改为消息列表**：不再逐帖推送完整详情
  - 新消息到达时发送一条含标题列表的摘要消息
  - 🆕 标识标记本轮新增的消息（关键词触发的常规列表不受影响）

### 调整

- `push_handler` 重写：移除 `_send_ordered_post`，新增 `_send_text`
- 推送格式：`🆕 1. 标题A (3图)\n🆕 2. 标题B (1图)`

---

## v0.2.11 - 2026-06-09

### 修复

- **图文顺序错误**：`parse_ordered_content` 改用 BeautifulSoup 按 DOM 顺序遍历
  - 正则方案存在边界 bug：多个连续 `<img>` 标签之间切分逻辑出错导致图片全堆末尾
  - BeautifulSoup 确保文本节点和图片严格按 HTML 顺序提取
- 删除不再使用的 `re` 导入

---

## v0.2.10 - 2026-06-09

### 修复

- **清除缓存后不重爬**：`/清除百分之一消息缓存` 执行后未重置 `_initial_crawl_done` 标志
  - 导致 `_ensure_crawled()` 认为已完成爬取，用户发关键词直接读空缓存
  - 清空命令中增加 `self._initial_crawl_done = False`

---

## v0.2.9 - 2026-06-09

### 新增

- **自动检测旧缓存**：插件加载时检测 `ordered_content` 为空的旧数据，自动清空并触发重爬
- **清除缓存命令**：`/清除百分之一消息缓存` 一键清空全部历史数据，下次查询时重新爬取最新消息
- `PostCache` 新增 `clear_all()` 和 `count_stale()` 方法
- `_conf_schema.json` 新增 `clear_history` 配置项说明清除缓存方法

---

## v0.2.7 - 2026-06-09

### 新增

- **图文按原文顺序混排**：
  - 新增 `PostItem.ordered_content` 字段，存储有序段落列表
  - 爬虫获取帖子后调用详情 API 获取 HTML 原文
  - `parse_ordered_content()` 解析 HTML 中的 `<img>` 标签，按原文顺序提取文本段和图片
  - `event.chain_result()` 按序构造 `[Plain(text), Image(url), Plain(text), ...]`
  - 推送同样使用 `ordered_content` 保持图文顺序

### 调整

- `TapTapClient` 新增 `fetch_post_detail(topic_id)` 调用详情接口
- `PostItem` 新增 `topic_id` 字段
- `PostCache` SQLite 表新增 `ordered_content` 列（兼容旧表 ALTER TABLE）
- `query_handler.handle_index_reply` 返回 `(bool, str, list[dict])` — ordered_content 替代 images

---

## v0.2.6 - 2026-06-09

### 修复

- **图文合并为一条消息**：改用 AstrBot 官方 `event.chain_result([Plain, Image, ...])` API
  - 之前用 `yield MessageChain()` 裸对象，框架管道不识别，消息被丢弃
  - `chain_result()` 是 `AstrMessageEvent` 官方方法，返回 `MessageEventResult`，框架正确解析
  - 图文按序在同一消息中展示

---

## v0.2.5 - 2026-06-09

### 修复

- **`Image(url=...)` 报错**：`Image.__init__()` 的 `file` 是位置参数，不是 `url=` 关键字
  - 改为 `Image(img_url)` 位置传参
  - push_handler 同步修复

---

## v0.2.4 - 2026-06-09

### 修复

- **图文分散为多条消息且顺序错误**：多 `yield` 导致框架每次发送独立消息
  - 改为构造单一 `MessageChain`：`[Plain(text), Image(url=url1), Image(url=url2), ...]`
  - 一次 `yield chain` → 框架收到完整图文链 → aiocqhttp 适配器一次发送
  - `Image(url=...)` 替代 `Image(file=...)` 以确保 HTTP URL 被正确解析

---

## v0.2.3 - 2026-06-09

### 修复

- **图片未渲染，显示为链接文本**：`plain_result` 不会解析 `[CQ:image]` CQ 码
  - 改用 `event.image_result(url)` 发送图片（AstrBot 标准图片 API）
  - 文本和图片分条发送：先文字、再逐张图

---

## v0.2.2 - 2026-06-09

### 修复

- **图片发送失败**：`Image(file=http_url)` 不被 aiocqhttp/NapCat 识别
  - 改用 `[CQ:image,file=<url>]` 嵌入文本，一条 `plain_result` 发出
  - 图文在同一消息中按序展示
- `push_handler` 方式二同步改为 `[CQ:image]` 嵌入式发送

---

## v0.2.1 - 2026-06-09

### 优化

- **图文合并为一条消息**：序号交互回复时，用 `MessageChain` 将文本和图片合并为单条混合消息
  - 之前：文本和图片分别 `yield` → 多条独立消息
  - 现在：`MessageChain([Plain(text), Image(file=url), ...])` → 一条消息

---

## v0.2.0 - 2026-06-09

### 新增

- **图片推送**：自动推送时附带帖子中的图片（aiocqhttp / NapCat）
- **图片查询**：序号交互查看详情时，发送帖内图片
- **图片数标识**：关键词触发列表显示每条消息的图片数量 `(N图)`

### 修复

- **图片提取路径错误**：`topic.images` 而非 `topic.footer_images.images`
  - 同时补充 `sharing.image`、`cover.image` 等兜底路径
  - 图片 URL 优先取 `original_url`（原图）

### 调整

- `query_handler` 接口变更：`handle_index_reply` 返回 `(bool, str, list[str])`
- `push_handler` 推送逻辑重写，支持构造 `MessageChain` 发送图文消息
- `main.py` 序号交互时 `yield event.image_result(img_url)` 发送图片
- 版本号更新到 0.2.0

---

## v0.1.6 - 2026-06-09

### 修复

- **爬虫获取 0 条**：`limit=20` 超出 TapTap API 限制（最大 10），请求返回 400
  - 改为 `limit=10`，已验证正常返回 10 条帖子
- **爬虫错误日志不可见**：所有模块统一改用 `from astrbot.api import logger`
  - 之前 `taptap_client/cache/parser/filter/handler` 用 `logging.getLogger(__name__)`，日志在 AstrBot 面板不可见，错误被静默吞掉
- 增强 HTTP 错误处理：记录 HTTP 状态码和响应体，区分网络异常和 API 业务错误

---

## v0.1.5 - 2026-06-09

### 修复

- **爬虫日志不可见**：改用 `from astrbot.api import logger` 替代 `logging.getLogger(__name__)`，确保日志在 AstrBot 面板中可见
- **首次交互仍返回"暂无消息"**：`on_message` 中关键词触发时改为 **同步等待** 爬取完成（`await self._ensure_crawled()`），再回复用户
- **移除不稳定的 `loop.call_later`**：改用 `on_message` 首次交互直接触发爬取，更简单可靠

### 调整

- 精简 `__init__`，移除延迟调度逻辑
- 首次爬取由用户首次发关键词时同步等待完成

---

## v0.1.4 - 2026-06-09

### 修复

- **爬虫热重载后仍不执行**：单层 `on_astrbot_loaded` 钩子在插件热重载时不触发
  - 改为三重保障：`loop.call_later(5)` 延迟调度 + `on_astrbot_loaded` 补充 + `on_message` 首次交互兜底
  - `_do_initial_crawl` 幂等设计，确保只执行一次

### 新增

- 爬取日志增强：每次爬取输出"本次获取 X 条，新增 Y 条，当前共 Z 条"
- 使用 emoji 标记关键日志（📋🔔🚀🔍📥❌），便于在 AstrBot 日志面板中快速定位

---

## v0.1.3 - 2026-06-09

### 修复

- **爬虫不执行**：移除 Playwright 依赖，改用 httpx + X_UA 直连 TapTap API（参照 RSSHub 方案）
  - 根因：AstrBot 事件循环在 `__init__` 阶段未就绪，`asyncio.ensure_future()` 无法启动爬虫
  - 改用 `@filter.on_astrbot_loaded()` 生命周期钩子延迟启动，AstrBot 完全加载后自动执行首次爬取
  - httpx 直连已验证可用（无需浏览器/Chromium）

### 调整

- 移除 `playwright` 依赖，减少部署环境要求
- 版本号更新到 0.1.3

---

## v0.1.2 - 2026-06-09

### 修复

- **致命 Bug**：修复 `_running` 永远为 False 导致 `on_message` 和爬虫均不执行的问题
  - 根因：`start()` 不是 AstrBot 生命周期钩子，AstrBot 只会调用 `__init__` 和 `terminate`
  - 修复：删除 `start()`，在 `__init__` 末尾调用 `_start_crawl()` 立即启动

### 调整

- 版本号从 0.1.0 更新到 0.1.2（metadata.yaml、pyproject.toml）

---

## v0.1.1 - 2026-06-08

### 修复

- 修复插件 `on_message` 未被 AstrBot 调用的 bug（缺少 `@filter.event_message_type(ALL)` 装饰器）
- 修复关键词/序号消息被 LLM 重复消费的问题（添加 `event.stop_event()`）
- 修复消息回复方式错误：`event.reply()` 不存在 → 改用 `yield event.plain_result()`
- 修复 `push_handler` 消息发送 API 不可用的问题（改用 `context.send_message` AstrBot 标准 API）

### 重构

- `query_handler` 改为纯数据层：`handle_keyword_trigger` / `handle_index_reply` 改为同步方法，返回 `(bool, str|None)` 元组
- 消息回复统一由 `main.py` 用 `yield` 方式发送

---

## v0.1.0 - 2026-06-08

### 新增

- 初始化项目目录结构和 Git 仓库
- 添加 Playwright 无头浏览器爬虫，支持 TapTap 用户动态获取
- 确认公开 API 端点：`/webapiv2/feed/v7/by-user`
- 实现 SQLite 消息缓存与去重
- 实现白名单/黑名单访问控制
- 实现关键词触发查询（默认：五维消息/百分之一消息/五维通知/百分之一通知）
- 实现序号交互查看详情
- 实现新消息自动推送到 QQ 群聊/私聊
- 添加 AstrBot WebUI 可视化配置（_conf_schema.json）
- 添加 README、.gitignore、.env.example

### 技术选型

- 依赖：httpx、beautifulsoup4、lxml、playwright
- 存储：SQLite（posts.db）
- 配置：AstrBot WebUI + _conf_schema.json

### 已知限制

- 需 AstrBot + NapCat 环境进行完整集成测试
- Playwright 首次使用需安装 Chromium（`playwright install chromium`）
