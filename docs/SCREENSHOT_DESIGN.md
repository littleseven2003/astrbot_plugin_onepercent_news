# 页面截图方案设计

## 目标
直接截取 TapTap 帖子页面的内容区域，生成长图，作为消息详情的图片消息发送。

## 技术方案

### 1. 浏览器引擎选择
- **Playwright** (推荐)
  - 支持 Chromium、Firefox、WebKit
  - 异步 API，与 AstrBot 的 asyncio 兼容
  - 支持全页面截图和元素截图
  - 可以等待特定元素加载完成

### 2. 页面 URL 结构
- 帖子详情页: `https://www.taptap.cn/moment/{post_id}`
- 需要确认页面是否需要 JavaScript 渲染（SPA 应用）

### 3. 内容区域定位
需要通过 CSS 选择器定位帖子内容区域。可能的方案：
- 查找包含帖子内容的 `<div>` 或 `<article>` 标签
- 使用 Playwright 的 `page.query_selector()` 或 `page.locator()`

### 4. 截图策略
1. **全页面截图**: `page.screenshot(full_page=True)`
2. **元素截图**: `element.screenshot()`
3. **长图处理**: 对于很长的内容，可能需要分段截图后拼接

### 5. 性能优化
- **浏览器实例复用**: 启动一个浏览器实例，多次使用
- **页面预加载**: 可以预先打开页面，减少等待时间
- **并发控制**: 限制同时打开的页面数量

### 6. 实现步骤
1. 创建 `crawler/page_screenshot.py` 模块
2. 实现 `ScreenshotRenderer` 类
3. 实现 `capture_post_screenshot(post_id)` 方法
4. 集成到 `push_handler.py` 和 `main.py`

### 7. 依赖
- `playwright>=1.40.0`
- 需要安装浏览器: `playwright install chromium`

### 8. 风险与对策
- **风险**: 部署环境可能无法安装 Chromium
  - **对策**: 提供 fallback 机制，如果截图失败则使用原有的图文混排方式
- **风险**: 截图速度慢
  - **对策**: 设置超时时间，超时后使用 fallback
- **风险**: 页面结构变化
  - **对策**: 使用相对稳定的 CSS 选择器，定期更新

## 代码结构

```
crawler/
├── page_screenshot.py  # 新增：页面截图模块
├── image_renderer.py   # 已有：Pillow 自绘模块（作为 fallback）
└── parser.py           # 已有：数据解析
```

## 使用示例

```python
from crawler.page_screenshot import capture_post_screenshot

# 截取帖子页面
image_buf = await capture_post_screenshot("468498237550217749")
if image_buf:
    # 发送图片
    chain = [Image(image_buf)]
    yield event.chain_result(chain)
else:
    # 使用 fallback
    # ...
```
