# 更新日志

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
