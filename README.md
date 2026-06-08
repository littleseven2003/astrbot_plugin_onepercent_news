# 百分之一消息推送插件

AstrBot 插件 —— 自动同步 TapTap 官方消息"五维互娱"到 QQ 群聊/私聊。

## 项目简介

游戏《百分之一》的官方运营账号"五维互娱"在 TapTap 论坛发布公告、活动、更新等消息。本插件通过 AstrBot 自动将官方消息同步到 QQ，让玩家在 QQ 中即可获取最新消息。

## 功能

- ✅ 定时爬取 TapTap 用户"五维互娱"的公开帖子
- ✅ 新消息自动推送到配置的 QQ 群聊/私聊
- ✅ 关键词触发查询（默认：`五维消息` / `百分之一消息` / `五维通知` / `百分之一通知`）
- ✅ 序号交互查看详情
- ✅ 白名单/黑名单模式控制推送范围
- ✅ 图文内容推送（帖子图片一并同步）

## 技术栈

- **框架**: AstrBot Star 插件框架
- **HTTP**: httpx（异步）
- **解析**: BeautifulSoup4 + lxml
- **存储**: SQLite（内置 sqlite3）
- **定时**: asyncio

## 快速开始

### 安装

将插件目录复制到 AstrBot 的 `addons` 目录下：

```bash
cp -r astrbot_plugin_onepercent_news /path/to/astrbot/addons/
```

### 依赖

依赖会在 AstrBot 加载插件时自动安装，或手动安装：

```bash
pip install httpx beautifulsoup4 lxml
```

使用 uv：

```bash
uv sync
```

### 配置

通过 AstrBot WebUI → 插件配置页面进行可视化配置。

主要配置项：

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `tap_uid` | TapTap 用户 ID | `19675784` |
| `crawl_interval` | 爬取间隔（秒） | `300` |
| `push_groups` | 自动推送目标群号 | `[]` |
| `push_privates` | 自动推送目标 QQ 号 | `[]` |
| `trigger_keywords` | 触发关键词 | `["五维消息", ...]` |
| `access_mode` | 名单模式 | `whitelist` |

## 文档

详细设计见：

```text
/docs/Design.md
```

## 环境变量

本插件无需额外环境变量。所有配置通过 AstrBot WebUI 管理。

## 版本

v0.1.0 - 首个可用原型（Phase 1: 项目初始化）
