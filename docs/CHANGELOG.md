# 更新日志

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
