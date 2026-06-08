# 项目设计文档：百分之一消息推送插件

## 1. 项目概述

### 1.1 项目名称
- 英文名：`astrbot_plugin_one_percent_news`
- 中文名：百分之一消息推送插件

### 1.2 项目背景
游戏《百分之一》的官方运营账号"五维互娱"在 TapTap 论坛发布公告、活动、更新等消息。玩家需要频繁手动打开 TapTap App 查看，体验较差。本项目通过 AstrBot 插件将官方消息自动同步到 QQ 群聊和私聊，让玩家在 QQ 中即可获取最新消息。

### 1.3 项目目标
1. 自动定时爬取 TapTap 用户"五维互娱"（uid=19675784）的公开消息/帖子；
2. 将新消息同步推送到指定的 QQ 群聊或私聊；
3. 支持关键词触发查询：用户在 QQ 中发送触发词后，机器人回复最近 10 条消息标题列表，用户回复数字序号即可查看详情；
4. 支持白名单/黑名单模式控制推送范围。

### 1.4 目标用户
- 《百分之一》游戏玩家；
- 安装了 AstrBot + NapCat 的 QQ 机器人管理员。

### 1.5 运行环境
- AstrBot（Python 插件框架）+ NapCat（QQ 协议端）；
- 消息平台适配器：aiocqhttp；
- Python 3.10+；
- 不需要独立数据库服务。

---

## 2. 功能范围

### 2.1 v1 必须实现
- ✅ 定时爬取 TapTap 用户"五维互娱"（uid=19675784）的公开帖子/动态列表；
- ✅ 新消息自动推送到配置的 QQ 群聊（支持多个群号）；
- ✅ 新消息自动推送到配置的 QQ 私聊（支持多个 QQ 号）；
- ✅ 关键词触发查询：收到触发关键词（默认 `五维消息` / `百分之一消息` / `五维通知` / `百分之一通知`，**可通过 WebUI 配置**）后，回复最近 10 条消息标题（编号 1-10）；
- ✅ 序号回复：用户回复数字（1-10）后，回复该条消息的详细内容（标题、正文摘要、发布时间、原帖链接、图片）；
- ✅ 白名单/黑名单模式切换：
  - 白名单模式：仅名单内的群聊/私聊可接收推送和触发查询；
  - 黑名单模式：名单内的群聊/私聊不接收推送和触发查询，其余均可；
- ✅ 爬取时使用公共浏览器 UA，不使用个人 Cookie/Token；
- ✅ 图文内容推送：推送消息时携带帖子中的图片（图片 URL），序号交互详情也包含图片；
- ✅ 通过 `_conf_schema.json` 提供 AstrBot WebUI 可视化配置（含触发关键词可配置）。

### 2.2 v1 暂不实现
- ❌ 管理员 Web 管理页面（使用 AstrBot 自带 WebUI 配插件配置）；
- ❌ 多游戏/多账号监控；
- ❌ 消息内容的 Markdown 渲染（v1 推送纯文本）。

### 2.3 后续可扩展
- 🔮 支持更多 TapTap 用户/游戏账号的监控；
- 🔮 消息分类过滤（公告 / 活动 / 更新日志 / 普通动态）；
- 🔮 自定义触发关键词；
- 🔮 爬取间隔热配置（无需重启）；
- 🔮 消息去重的持久化（SQLite 替代内存缓存）。

---

## 3. 技术栈选择

### 3.1 插件框架
- **AstrBot Star 插件框架**：继承 `Star` 类，使用 `@filter.command` 和 `@filter.event_message_type` 装饰器注册消息处理器。

### 3.2 HTTP 客户端
- **httpx**（异步）：用于向 TapTap 发送 HTTP 请求，支持自定义 Headers（UA）、超时、重试。

### 3.3 HTML 解析（备选方案）
- **BeautifulSoup4 + lxml**：当 TapTap 公开 API 不可用时，作为 HTML 页面解析的备选方案。

### 3.4 数据存储
- **SQLite**（Python 内置 `sqlite3`，零额外依赖）：存储已推送消息的完整内容（用于去重、关键词查询、序号交互）。JSON 文件读写在高频爬取场景下性能差、不支持增量更新，SQLite 是更好的选择且无需额外安装。
- **JSON 文件**：仅保留白名单/黑名单配置（`access_list.json`），数据量极小，JSON 足够。

### 3.5 定时任务
- **asyncio.create_task()**：在插件 `__init__` 中创建异步循环任务，按可配置的间隔爬取。

### 3.6 技术栈选择理由
| 考量 | 选择 | 理由 |
|---|---|---|
| 框架 | AstrBot Star | 用户已明确环境为 AstrBot，插件必须为 Star 类 |
| HTTP | httpx | 异步、API 友好、原生支持自定义 Headers 和超时 |
| 解析 | BeautifulSoup4 | TapTap 页面可能重度 JS 渲染，API 不可用时需 HTML 解析兜底 |
| 存储 | SQLite + JSON | SQLite 存储消息内容（去重+查询，零额外依赖），JSON 仅存白名单/黑名单配置 |
| 定时 | asyncio | 轻量，无需引入 Celery/APScheduler 等额外依赖 |

---

## 4. 系统架构

```text
TapTap 服务器（公开页面/API）
       ↑
       | httpx 定时请求（带浏览器 UA）
       |
+----------------------------+
|  AstrBot Plugin             |
|  one_percent_news           |
|                             |
|  ┌──────────────────────┐   |
|  │  Crawler 爬虫模块     │   |
|  │  - 定时获取帖子列表    │   |
|  │  - 检测新内容         │   |
|  │  - HTML/API 解析      │   |
|  └──────────┬───────────┘   |
|             ↓               |
|  ┌──────────────────────┐   |
|  │  Cache 缓存模块       │   |
|  │  - 已推送消息 ID 去重 │   |
|  │  - 消息详情缓存       │   |
|  └──────────┬───────────┘   |
|             ↓               |
|  ┌──────────────────────┐   |
|  │  Filter 过滤模块      │   |
|  │  - 白名单/黑名单判断  │   |
|  │  - 关键词匹配         │   |
|  └──────────┬───────────┘   |
|             ↓               |
|  ┌──────────────────────┐   |
|  │  Handler 消息处理模块 │   |
|  │  - 关键词触发回复     │   |
|  │  - 序号交互流程       │   |
|  │  - 自动推送           │   |
|  └──────────┬───────────┘   |
|             ↓               |
+----------------------------+
       ↓
   AstrBot Core（aiocqhttp 适配器）
       ↓
   NapCat（QQ 协议端）
       ↓
   QQ 群聊 / QQ 私聊
```

---

## 5. 目录结构

```text
astrbot_plugin_one_percent_news/
├── README.md                         # 插件说明文档
├── design.md                         # 本设计文档
├── metadata.yaml                     # AstrBot 插件元数据
├── _conf_schema.json                 # AstrBot WebUI 配置 Schema
├── requirements.txt                  # Python 依赖
├── main.py                           # 插件入口：Star 子类 + 消息 Handler
├── crawler/
│   ├── __init__.py
│   ├── taptap_client.py              # TapTap HTTP 请求封装（UA、超时、重试）
│   └── parser.py                     # 响应解析（JSON API 优先，HTML fallback）
├── cache/
│   ├── __init__.py
│   └── post_cache.py                 # 消息缓存 & 去重（SQLite 读写）
├── filter/
│   ├── __init__.py
│   └── access_control.py             # 白名单/黑名单判断逻辑
├── handler/
│   ├── __init__.py
│   ├── query_handler.py              # 关键词触发 → 列表回复 → 序号交互
│   └── push_handler.py               # 自动推送新消息到群/私聊
└── data/
    ├── posts.db                      # SQLite 数据库（运行时自动创建，存储消息全量）
    └── access_list.json              # 白名单/黑名单持久化（运行时自动创建）
```

---

## 6. 核心模块设计

### 6.1 爬虫模块（crawler/）

#### 6.1.1 taptap_client.py
- **职责**：封装对 TapTap 的所有 HTTP 请求。
- **核心功能**：
  - 构造请求 Headers：`User-Agent` 使用 Chrome/Edge 最新稳定版 UA（可配置）；
  - 超时与重试：默认超时 15s，失败重试 2 次，指数退避；
  - 支持两种请求方式：
    1. **API 优先**：尝试调用 TapTap WebAPIV2 公开接口（如用户动态列表接口）；
    2. **HTML 兜底**：当 API 不可用时，请求用户主页 HTML 并提取内嵌数据。
- **关键参数**：
  - `uid`: 19675784（五维互娱的用户 ID）
  - `page_size`: 20（每次获取条数）
  - `user_agent`: 从配置读取，默认 `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...`

#### 6.1.2 parser.py
- **职责**：解析 TapTap 返回的原始数据，提取统一的消息结构。
- **核心功能**：
  - JSON 解析路径：适配 TapTap API 的 JSON 结构（开发阶段通过抓包确认）；
  - HTML 解析路径：使用 BeautifulSoup 从 HTML 中提取帖子列表；
  - 输出统一数据结构：`PostItem(id, title, summary, url, published_at, post_type, images)`
  - `images` 为图片 URL 列表，从帖子正文中提取

### 6.2 缓存模块（cache/）

#### 6.2.1 post_cache.py
- **职责**：管理已获取的消息，提供去重和查询能力。
- **核心功能**：
  - 插件启动时自动创建 SQLite 表（`CREATE TABLE IF NOT EXISTS`）；
  - `is_new(post_id) -> bool`：查询消息是否已存在（SQLite `SELECT`）；
  - `mark_pushed(post: PostItem)`：插入新消息记录；
  - `get_recent_posts(n: int) -> list[PostItem]`：按发布时间倒序获取最近 n 条消息；
  - `get_post_by_index(index, n) -> PostItem`：从最近 n 条中按序号获取单条消息；
  - `prune_old_posts(max_keep: int)`：保留最近 `max_history` 条记录，自动清理超出的旧数据；
  - SQLite 文件存储在 `data/posts.db`，无需用户手动创建。
- **SQLite 优势**：
  - 增量读写（不需要每次都序列化整个 JSON）；
  - 支持索引（按 `published_at` 索引，查询快）；
  - 自然支持并发控制（插件定时爬取 + 用户查询同时发生不冲突）；
  - 数据量可控：`max_history` 条 × 每条约 2KB = 总大小 < 1MB。

### 6.3 过滤模块（filter/）

#### 6.3.1 access_control.py
- **职责**：判断某个会话（群聊/私聊）是否有权限接收消息。
- **核心功能**：
  - 支持四种模式组合：
    - `group_whitelist` / `group_blacklist`
    - `private_whitelist` / `private_blacklist`
  - `check_group(group_id) -> bool`：群聊是否通过；
  - `check_private(user_id) -> bool`：私聊是否通过；
  - 名单持久化到 `data/access_list.json`；
  - 支持通过 AstrBot 指令动态添加/移除名单（v1 可选）。

### 6.4 消息处理模块（handler/）

#### 6.4.1 query_handler.py
- **职责**：处理用户在 QQ 中的关键词触发和序号交互。
- **核心功能**：
  - 关键词匹配：`五维消息` / `百分之一消息` / `五维通知` / `百分之一通知`（精确匹配或包含匹配）；
  - 列表回复：返回最近 10 条消息的标题和序号（如关键词不在默认列表中，以 WebUI 配置的 `trigger_keywords` 为准）；
  - 序号交互：用户回复纯数字 1-10 后，查询对应消息详情并回复（含标题、正文摘要、发布时间、原帖链接、图片）；
  - 交互状态管理：用内存 dict 记录等待序号输入的用户（key=`group_id+user_id`，60s 超时自动清理）。

#### 6.4.2 push_handler.py
- **职责**：将新消息主动推送到配置的目标会话。
- **核心功能**：
  - 遍历配置的推送目标（群聊列表 + 私聊列表）；
  - 通过白名单/黑名单过滤；
  - 调用 AstrBot 消息发送 API 推送；
  - 推送内容格式：`【百分之一消息】{标题}\n{摘要}\n{链接}`，有图片时附带图片 URL（aiocqhttp 支持在纯文本消息中包含图片 URL，NapCat 会自动渲染为图片）；
  - 如消息含多张图片，只推送第一张（避免刷屏），其余以链接形式附加。

### 6.5 主入口模块（main.py）
- **职责**：插件入口，整合所有模块。
- **核心功能**：
  - 继承 `Star` 类；
  - `__init__` 中：读取配置、初始化各模块、启动后台定时爬取任务；
  - 注册消息 Handler：
    - `@filter.command("五维消息")` 等（或使用 `on_message` 事件 + 自定义匹配）；
    - 监听所有消息事件，匹配触发词和序号交互；
  - 实现 `terminate()` 清理资源。

---

## 7. 配置设计（_conf_schema.json）

由于本插件是 AstrBot 插件，不提供 REST API，而是通过 AstrBot 的配置系统暴露可配置项。

### 7.1 配置项一览

| 配置键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `tap_uid` | string | `"19675784"` | TapTap 用户 ID |
| `user_agent` | string | Chrome 128 UA | 爬虫使用的浏览器 UA |
| `crawl_interval` | int | `300` | 爬取间隔（秒），默认 5 分钟 |
| `crawl_timeout` | int | `15` | HTTP 请求超时（秒） |
| `crawl_retry` | int | `2` | 失败重试次数 |
| `access_mode` | string | `"whitelist"` | 名单模式：`whitelist` 或 `blacklist` |
| `group_list` | array[string] | `[]` | 群聊白名单/黑名单（群号列表） |
| `private_list` | array[string] | `[]` | 私聊白名单/黑名单（QQ号列表） |
| `push_groups` | array[string] | `[]` | 自动推送目标群号列表 |
| `push_privates` | array[string] | `[]` | 自动推送目标 QQ 号列表 |
| `trigger_keywords` | array[string] | `["五维消息","百分之一消息","五维通知","百分之一通知"]` | 触发关键词 |
| `list_count` | int | `10` | 关键词触发时返回的消息条数 |
| `max_history` | int | `200` | SQLite 中保留的历史消息上限（超出自动清理旧数据） |
| `interaction_timeout` | int | `60` | 序号交互超时（秒） |

### 7.2 _conf_schema.json 示例（核心字段）

```json
{
  "tap_uid": {
    "description": "TapTap 用户 ID",
    "type": "string",
    "default": "19675784"
  },
  "user_agent": {
    "description": "爬虫浏览器 UA",
    "type": "string",
    "default": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
  },
  "crawl_interval": {
    "description": "爬取间隔（秒）",
    "type": "int",
    "default": 300
  },
  "access_mode": {
    "description": "名单模式",
    "type": "string",
    "options": ["whitelist", "blacklist"],
    "default": "whitelist"
  },
  "group_list": {
    "description": "群聊名单（群号列表，一行一个）",
    "type": "list",
    "default": []
  },
  "private_list": {
    "description": "私聊名单（QQ号列表，一行一个）",
    "type": "list",
    "default": []
  },
  "push_groups": {
    "description": "自动推送目标群号",
    "type": "list",
    "default": []
  },
  "push_privates": {
    "description": "自动推送目标 QQ 号",
    "type": "list",
    "default": []
  },
  "trigger_keywords": {
    "description": "触发关键词（一行一个）",
    "type": "list",
    "default": ["五维消息", "百分之一消息", "五维通知", "百分之一通知"]
  },
  "list_count": {
    "description": "关键词触发时返回的消息条数",
    "type": "int",
    "default": 10
  },
  "max_history": {
    "description": "SQLite 中保留的历史消息上限（最小 10，超出自动清理旧数据）",
    "type": "int",
    "default": 200
  },
  "interaction_timeout": {
    "description": "序号交互超时（秒）",
    "type": "int",
    "default": 60
  }
}
```

---

## 8. 数据设计

### 8.1 核心数据结构

#### PostItem（内存中）
```python
@dataclass
class PostItem:
    post_id: str          # 帖子唯一 ID（TapTap 分配）
    title: str            # 帖子标题
    summary: str          # 内容摘要（前 200 字）
    url: str              # 原帖链接
    published_at: str     # 发布时间（ISO 8601）
    images: list[str]     # 图片 URL 列表（正文中的图片）
    post_type: str        # 类型：announcement / activity / normal
```

#### SQLite：posts 表（`data/posts.db`）

```sql
CREATE TABLE IF NOT EXISTS posts (
    post_id      TEXT PRIMARY KEY,       -- TapTap 帖子唯一 ID（去重主键）
    title        TEXT NOT NULL,          -- 帖子标题
    summary      TEXT,                   -- 内容摘要（前 200 字）
    url          TEXT NOT NULL,          -- 原帖链接
    published_at TEXT NOT NULL,          -- 发布时间（ISO 8601）
    images       TEXT,                   -- 图片 URL 列表（JSON 数组字符串）
    post_type    TEXT DEFAULT 'normal',  -- 类型：announcement/activity/normal
    created_at   TEXT DEFAULT (datetime('now','localtime'))  -- 入库时间
);

-- 索引：按发布时间倒序查询（关键词触发列表）
CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published_at DESC);
```

- **去重策略**：`post_id` 为主键，`INSERT OR IGNORE` 自然去重，无需额外 `pushed_ids` 表；
- **查询最近消息**：`SELECT * FROM posts ORDER BY published_at DESC LIMIT ?`；
- **序号详情**：从最近 N 条结果中取第 index 条；
- **自动清理**：每次爬取后执行 `DELETE FROM posts WHERE post_id NOT IN (SELECT post_id FROM posts ORDER BY published_at DESC LIMIT ?)`，保留最近 `max_history` 条；
- **预估体积**：200 条 × 约 2KB/条（含图片 URL）= 约 400KB，完全可控。

#### access_list.json（持久化名单）
```json
{
  "access_mode": "whitelist",
  "group_list": ["123456789", "987654321"],
  "private_list": ["10001", "10002"],
  "push_groups": ["123456789"],
  "push_privates": []
}
```

### 8.2 数据流

```text
定时任务触发
  → taptap_client 请求 TapTap
    → parser 解析为 PostItem 列表
      → post_cache.is_new(post_id) 查 SQLite 去重
        → 新消息 → push_handler 推送到目标群/私聊
        → post_cache.mark_pushed(post) 写入 SQLite
        → post_cache.prune_old_posts(max_history) 清理超出上限的旧数据

用户发送关键词
  → query_handler 匹配触发
    → access_control 权限检查
      → post_cache.get_recent_posts(list_count) 从 SQLite 查询
        → 回复标题列表

用户回复序号
  → query_handler 匹配序号
    → post_cache.get_post_by_index(n, list_count) 从 SQLite 查询
      → 回复详情
```

---

## 9. TapTap 数据获取策略

> ⚠️ **重要风险提示**：TapTap 前端页面重度依赖 JavaScript 渲染，公开 WebAPI 端点可能随时间变化或需要特定鉴权参数。本节给出分层获取策略。

### 9.1 策略一：公开 API（优先尝试）
在浏览器 DevTools → Network → XHR 中抓包，找到 TapTap Web 端调用的用户动态 API。常见路径模式：
- `/webapiv2/moment/v4/user-moment-list`
- `/webapiv2/feed/v7/user-post`

请求时携带：
- 标准浏览器 `User-Agent`
- `Referer: https://www.taptap.cn/user/19675784`
- 不携带任何 Cookie/Token

### 9.2 策略二：HTML 内嵌数据解析（兜底）
如果公开 API 需要鉴权，改为请求用户主页 HTML：
- `GET https://www.taptap.cn/user/19675784/moment`
- 使用 BeautifulSoup 提取页面内嵌的 `__NEXT_DATA__` 或 `<script>` 中的 JSON 数据；
- 或解析 HTML DOM 树中的帖子列表。

### 9.3 策略三：移动端 API（备选）
TapTap 移动端 API 通常鉴权更宽松，可通过抓包 App 请求获取端点。

### 9.4 爬取频率控制
- v1 默认 5 分钟一次，最低不低于 60 秒；
- 每次请求间隔至少 3 秒，避免触发反爬；
- 请求失败时指数退避重试（2s → 4s → 8s）。

---

## 10. 安全与限制

- ✅ **不使用个人 Cookie/Token**：所有请求仅携带标准浏览器 UA，不绑定任何用户身份；
- ✅ **爬取频率限制**：最低 60 秒间隔，避免对 TapTap 服务器造成压力；
- ✅ **环境变量保护**：虽然是公开爬取，但如后续版本需要 API Key，必须通过 AstrBot 配置系统管理，不硬编码；
- ✅ **名单安全**：白名单/黑名单仅影响消息推送范围，不影响 AstrBot 核心安全；
- ✅ **错误日志**：爬取失败、解析失败、推送失败均记录日志，不抛出未捕获异常导致插件崩溃；
- ✅ **交互状态超时**：序号交互 60 秒超时，防止内存泄漏。

---

## 11. 开发阶段建议

### Phase 1: 项目初始化 + TapTap API 探索
- [ ] 创建插件目录结构；
- [ ] 编写 `metadata.yaml`、`requirements.txt`、`_conf_schema.json`；
- [ ] 编写 `main.py` 最小可用 Star 插件骨架；
- [ ] **关键任务**：通过浏览器 DevTools 抓包，确定 TapTap 用户动态的公开 API 端点和响应结构；
- [ ] 编写 `taptap_client.py` + `parser.py`，实现单次请求并成功解析帖子列表；
- [ ] 单元测试：手动触发爬取，验证能正确获取五维互娱的帖子；
- [ ] Git 提交。

### Phase 2: 缓存 + 推送闭环
- [ ] 编写 `post_cache.py`，实现 JSON 文件读写 + 去重；
- [ ] 编写 `push_handler.py`，实现向指定群聊/私聊推送消息；
- [ ] 在 `main.py` 中注册 `asyncio.create_task()` 后台定时任务；
- [ ] 集成测试：启动插件，验证新帖自动推送到目标 QQ 群；
- [ ] Git 提交。

### Phase 3: 关键词交互
- [ ] 编写 `access_control.py`，实现白名单/黑名单逻辑；
- [ ] 编写 `query_handler.py`，实现关键词触发 → 列表回复 → 序号交互；
- [ ] 在 `main.py` 中注册消息 Handler；
- [ ] 集成测试：在 QQ 群发送"五维消息"，验证列表回复和序号交互；
- [ ] Git 提交。

### Phase 4: 配置完善 + 部署文档
- [ ] 完善 `_conf_schema.json`，确保所有配置项在 WebUI 可见可编辑；
- [ ] 编写 `README.md`（安装步骤、配置说明、使用示例）；
- [ ] 边缘情况处理：空列表（无新消息）、TapTap 不可达、解析失败降级；
- [ ] 在 AstrBot + NapCat 环境完整测试；
- [ ] Git 提交 + 打 v1.0.0 tag。

---

## 12. 给开发 Agent 的提示词

> 请根据本 `design.md` 实现 `astrbot_plugin_one_percent_news` 插件。要求：

1. **严格遵循 v1 功能范围**（见第 2 节），不要擅自扩大 scope；
2. **优先完成 TapTap API 发现**（Phase 1 关键任务）—— 通过浏览器 DevTools 抓包确定正确的 API 端点和响应 JSON 结构，再开始写爬虫代码；
3. **使用公开请求**—— 爬取时只携带浏览器 UA 头，不携带任何 Cookie、Token 或用户身份信息；
4. **按 Phase 顺序开发**，每完成一个 Phase 进行一次 Git 提交，提交信息格式：`feat(phase-N): xxx`；
5. **不要引入设计文档之外的大型依赖**（如数据库 ORM、消息队列、Redis 等），v1 保持轻量；
6. **优先保证可运行**—— 插件能在 AstrBot + NapCat + aiocqhttp 环境下正常加载和工作；
7. **错误不崩溃**—— 所有爬取、解析、推送异常必须捕获并记录日志，不能导致插件崩溃或 AstrBot 主进程退出；
8. **如发现设计不合理之处**，先在 `design.md` 末尾追加 `## 附录：设计修订记录` 记录建议，再进行最小改动。
