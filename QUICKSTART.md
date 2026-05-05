# 快速开始指南

当前项目主链已经收敛为 `iOS 手动抓包 + 实时结构化 + 数据管理 + Playwright 电话补抓`，不再按旧版节点编排流程启动。

## 第一步：安装依赖

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test

# 推荐先创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

说明：

- 当前项目不需要 `uv`，直接使用 `venv + pip` 即可。
- 推荐使用 `Python 3.11+`。
- `requirements.txt` 已包含 `playwright`。
- 默认优先使用本机 Chrome/Chromium，不强制安装 Playwright 自带浏览器。
- 只有在需要 Playwright 自带浏览器时，才执行 `python -m playwright install chromium`。

## 第二步：启动桌面端

```bash
python node_editor_app.py
```

当前桌面端页面：

1. 抓取实时数据
2. 数据管理
3. 抓包配置

## 第三步：本地测试校验

```bash
python3 -m py_compile node_editor_app.py gui/capture/capture_only_window.py gui/capture/*.py integration/http_capture.py
python3 -m unittest test_auth_service.py
```

## 第四步：运行 Playwright 独立补抓

```bash
# 默认优先使用本机 Chrome/Chromium
./start_playright.sh
```

常用参数：

```bash
./start_playright.sh --limit 5
./start_playright.sh --browser-path "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

## 第五步：查看日志

日志文件保存在 `logs/`

```bash
tail -f logs/*.log
```

## 常见问题

### Q1: `pip install -r requirements.txt` 失败怎么办？

**A:** 优先检查 Python 版本。当前建议统一使用 `Python 3.11+`，尤其是 `mitmproxy` 与打包流水线环境。

### Q2: 为什么 `main.py` 不能作为当前入口？

**A:** 当前桌面发布入口已经收敛为 `node_editor_app.py -> gui/capture/capture_only_window.py`。`main.py` 属于旧链路，不再用于当前桌面主流程或 CI。

### Q3: 当前正式多平台构建读取哪个配置？

**A:** 当前正式多平台构建读取 `.github/workflows/cross-platform-build.yml`。如果 Gitee 侧还保留旧的 `branch-pipeline`，建议停用，避免和 GitHub Actions 混用。

```python
from core.node_executor import NodeExecutor
from core.screen_capture import ScreenCapture
from core.click_simulator import ClickSimulator
from core.template_matcher import TemplateMatcher
from core.coordinate_cache import CoordinateCache
from config.settings import Settings

# 初始化
screen = ScreenCapture()
clicker = ClickSimulator()
matcher = TemplateMatcher(str(Settings.TEMPLATE_DIR), screen)
cache = CoordinateCache(str(Settings.CACHE_FILE))
executor = NodeExecutor(matcher, clicker, cache)

# 测试节点
node = {
    'id': 'test',
    'name': '测试节点',
    'type': 'click',
    'template': 'food_button.png',
    'threshold': 0.85
}

result = executor.execute_node(node)
print(f"执行结果: {result}")
```

## 高级配置

### 调整滚动参数

编辑 `config/settings.py`：

```python
SCROLL = {
    'distance': 500,    # 滚动距离（像素）
    'duration': 0.5,    # 滚动时长（秒）
    'max_scrolls': 100, # 最大滚动次数
}
```

### 调整重试策略

编辑 `config/settings.py`：

```python
RETRY = {
    'max_attempts': 3,      # 最大重试次数
    'backoff_factor': 1.5,  # 退避因子
    'initial_wait': 1.0,    # 初始等待时间（秒）
}
```

### 调整延迟时间

编辑 `config/settings.py`：

```python
DELAYS = {
    'click_min': 0.1,      # 最小点击延迟
    'click_max': 0.3,      # 最大点击延迟
    'page_load': 1.0,      # 页面加载等待
    'filter_apply': 0.8,   # 筛选应用等待
}
```

## 下一步

1. 根据实际情况调整配置参数
2. 为每个区域准备文字模板（可选）
3. 集成Rust抓包工具
4. 添加数据导出功能

## 技术支持

如有问题，请查看：
- 日志文件：`logs/automation_YYYY-MM-DD.log`
- README文档：`README.md`
- 需求文档：`需求文档.md`
