# 百分之一消息推送插件

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Version](https://img.shields.io/badge/version-1.1.6-blue)

AstrBot 插件 —— 自动同步 TapTap 官方消息"五维互娱"到 QQ 群聊/私聊。

---

## 项目简介

游戏《百分之一》的官方运营账号"五维互娱"在 TapTap 论坛发布公告、活动、更新等消息。本插件通过 AstrBot 自动将官方消息同步到 QQ，让玩家在 QQ 中即可获取最新消息。

---

## 面向用户

### 功能

- ✅ 定时爬取 TapTap 用户"五维互娱"的公开帖子（默认 10 分钟一次）
- ✅ 新消息自动推送到 QQ 群聊/私聊
- ✅ 关键词触发查询：发送关键词后回复最近 10 条消息标题，回复数字查看详情
- ✅ 图文内容推送：帖子中的图片按原帖顺序混排展示
- ✅ 黑白名单控制（群聊和私聊可分别独立设置）
- ✅ 管理员命令：`/刷新百分之一消息`、`/清除百分之一消息缓存`
- ✅ WebUI 可视化配置所有参数

### 安装

1. 在 AstrBot WebUI → 插件管理页面 → 上传插件包 `astrbot_plugin_onepercent_news-x.x.x.zip`
2. 或手动复制插件目录到 AstrBot 的 `addons` 目录下
3. 依赖会在安装时自动处理

```bash
# 手动安装依赖（可选）
pip install httpx beautifulsoup4 lxml Pillow playwright

# 如需使用「图片消息」模式，还需安装 Chromium 浏览器
playwright install chromium
```

### 配置

通过 AstrBot WebUI → 插件配置页面进行可视化配置。

#### 基础配置

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `tap_uid` | TapTap 用户 ID | `19675784` |
| `crawl_interval` | 爬取间隔（秒），最低 60 | `300` |
| `trigger_keywords` | 触发关键词（每行一个） | `五维消息` / `百分之一消息` / `五维通知` / `百分之一通知` |
| `list_count` | 触发关键词时返回的消息条数 | `10` |
| `interaction_timeout` | 序号交互超时（秒） | `60` |
| `max_history` | SQLite 缓存上限（条） | `200` |
| `push_mode` | 推送展示方式：`list`（标题列表）或 `detail`（逐条详情） | `detail` |
| `detail_display_mode` | 详情展示方式：`text_image`（图文混排）或 `image`（截图为长图） | `text_image` |

> **图片消息模式说明**：使用 `image` 模式需在服务器执行 `playwright install chromium` 安装浏览器。未安装时会自动回退到图文混排模式。

#### 群聊/私聊独立黑白名单

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `group_access_mode` | 群聊模式：`blacklist` 或 `whitelist` | `blacklist` |
| `group_blacklist` | 群聊黑名单（列表为空则全部允许） | `[]` |
| `group_whitelist` | 群聊白名单（列表为空则全部禁止） | `[]` |
| `private_access_mode` | 私聊模式：`blacklist` 或 `whitelist` | `blacklist` |
| `private_blacklist` | 私聊黑名单（列表为空则全部允许） | `[]` |
| `private_whitelist` | 私聊白名单（列表为空则全部禁止） | `[]` |

**逻辑规则：**

| 模式 | 名单为空 | 名单不为空 |
|---|---|---|
| 黑名单 | 全部允许 | 名单内禁止，其余允许 |
| 白名单 | 全部禁止 | 名单内允许，其余禁止 |

**自动推送**：白名单模式下自动推送到名单中的所有群/用户；黑名单模式下推送所有交互过的群/用户（已按黑名单过滤）。

#### 管理员

| 配置项 | 说明 |
|---|---|
| `admin_qq` | 管理员 QQ 号列表（拥有 `/清除百分之一消息缓存` 和 `/刷新百分之一消息` 权限） |

### 使用方式

在 QQ 群聊或私聊中发送以下关键词：

| 命令 | 行为 | 权限 |
|---|---|---|
| `五维消息` / `百分之一消息` 等 | 返回最近 10 条消息标题列表 | 所有人 |
| 回复数字 `1`-`10` | 查看该条消息详情（含图片） | 所有人 |
| `/刷新百分之一消息` | 立即执行一次爬取刷新 | 管理员 |
| `/清除百分之一消息缓存` | 清空全部缓存重新爬取 | 管理员 |

---

## 面向开发者

### 技术栈

| 组件 | 选型 | 理由 |
|---|---|---|
| 框架 | AstrBot Star | 插件框架 |
| HTTP | httpx（异步） | 轻量、支持自定义 Headers |
| HTML 解析 | BeautifulSoup4 + lxml | 提取详情页图文顺序 |
| 存储 | SQLite（内置 sqlite3） | 零额外依赖、支持去重和查询 |
| 定时 | asyncio | 轻量，无需 APScheduler |

### 目录结构

```
astrbot_plugin_onepercent_news/
├── main.py                    # 插件入口（Star 类 + 消息 Handler + 命令）
├── metadata.yaml              # AstrBot 插件元数据
├── _conf_schema.json          # WebUI 配置 Schema
├── requirements.txt           # Python 依赖
├── crawler/
│   ├── taptap_client.py       # TapTap API 请求（httpx + X_UA）
│   └── parser.py              # JSON/HTML 解析 + PostItem 数据结构
├── cache/
│   └── post_cache.py          # SQLite 消息缓存与去重
├── filter/
│   └── access_control.py      # 群聊/私聊独立黑白名单
├── handler/
│   ├── query_handler.py       # 关键词触发 + 序号交互
│   └── push_handler.py        # 自动推送新消息
└── data/                      # 运行时数据（SQLite + JSON）
```

### API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/webapiv2/feed/v7/by-user` | GET | 获取用户动态列表 |
| `/webapiv2/topic/v1/detail` | GET | 获取帖子详情（含 HTML 原文） |

**认证方式**：公开 API，仅需 `X_UA` 查询参数（参照 [RSSHub](https://github.com/DIYgod/RSSHub) 公式），无需 Cookie/Token。

### 数据流

```
定时任务 / 手动刷新
  → taptap_client.fetch_user_moments()
    → feed API 获取帖子列表 (limit=10)
      → parser.parse() 解析为 PostItem
        → 逐帖调用 detail API → parse_ordered_content() 提取图文顺序
          → post_cache.mark_pushed() 写入 SQLite
            → push_handler.push_new_posts() 推送新消息列表

用户发关键词
  → query_handler 匹配触发
    → post_cache.get_recent_posts() 从 SQLite 查询
      → 回复标题列表

用户回复序号
  → query_handler.handle_index_reply()
    → post_cache.get_post_by_index() 查询
      → event.chain_result([Plain, Image, ...]) 图文混排回复
```

### 示例：解析帖子详情图文顺序

```python
from crawler.parser import PostParser

html = """活动时间：06月1日<br/>
<img data-origin-url="https://img.tapimg.com/xxx.png"><br/>
6月23再次优化活动..."""

ordered = PostParser.parse_ordered_content(html)
# [
#   {"type": "text", "text": "活动时间：06月1日"},
#   {"type": "image", "url": "https://img.tapimg.com/xxx.png"},
#   {"type": "text", "text": "6月23再次优化活动..."},
# ]
```

### 开发环境

```bash
git clone https://github.com/littleseven2003/astrbot_plugin_onepercent_news.git
cd astrbot_plugin_onepercent_news
uv sync
```

---

## 免责声明

- **本插件仅爬取 TapTap 公开页面数据**，不携带任何用户 Cookie、Token 或身份信息。
- **爬取频率受控**（默认 5 分钟一次，最低 60 秒），不对 TapTap 服务器造成压力。
- **插件仅供学习交流使用**，使用者应遵守 TapTap 平台的 [robots.txt](https://www.taptap.cn/robots.txt) 及相关服务条款。
- **作者不对因使用本插件产生的任何后果负责**，包括但不限于账号封禁、数据丢失等。

---

## 二次开发

欢迎 PR 和 Issue！

如需二次开发，请注意：
- **爬取频率**：请勿将 `crawl_interval` 设置过低（≥60 秒），避免对 TapTap 服务器造成负担。
- **公开数据**：请勿携带 Cookie/Token 请求 API，保持公开访问原则。
- **错误处理**：爬虫、解析、推送的所有异常都已捕获并记录日志，二次开发时请保持这一原则。
- **配置兼容**：`_conf_schema.json` 中各字段加字段遵循 AstrBot 规范；改动后需同步更新 `main.py` 中的默认值。
- **遵守法律法规**：请勿将插件用于非法用途。

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

```
MIT License

Copyright (c) 2026 littleseven2003

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 版本历史

详见 [/docs/CHANGELOG.md](docs/CHANGELOG.md)
