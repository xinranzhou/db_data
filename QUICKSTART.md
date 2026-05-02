# 快速开始指南

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
- `requirements.txt` 已包含 `playwright`。
- 默认优先使用本机 Chrome/Chromium，不强制安装 Playwright 自带浏览器。
- 只有在需要 Playwright 自带浏览器时，才执行 `python -m playwright install chromium`。

## 第二步：测试系统

```bash
# 运行测试脚本，确保所有模块正常工作
python test_system.py
```

预期输出：
```
✓ 截屏功能: 通过
✓ 点击模拟: 通过
✓ 模板匹配: 通过
✓ 坐标缓存: 通过
✓ 配置文件: 通过
```

## 第三步：配置节点（使用GUI编辑器）

```bash
# 启动GUI节点编辑器
python node_editor_app.py
```

### 配置示例节点

#### 节点1：点击美食按钮

1. 点击"新建节点"
2. 填写信息：
   - 名称：`点击美食`
   - 类型：`click`
   - 匹配阈值：`0.85`
   - 勾选"初始化节点"
3. 点击"截图并框选"
   - 窗口会最小化
   - 打开大众点评小程序到首页
   - 1秒后会自动截屏
   - 拖拽鼠标框选"美食"按钮
   - 按Enter确认
4. 模板会自动保存为 `food_button.png`
5. 点击"保存节点"

#### 节点2：验证列表页

1. 点击"新建节点"
2. 填写信息：
   - 名称：`验证列表页`
   - 类型：`verify`
   - 匹配阈值：`0.7`
   - 勾选"初始化节点"
3. 点击"截图并框选"
   - 打开大众点评小程序到美食列表页
   - 框选筛选栏或列表卡片
   - 按Enter确认
4. 点击"保存节点"

#### 节点3：点击区域筛选

1. 点击"新建节点"
2. 填写信息：
   - 名称：`点击区域筛选`
   - 类型：`click`
   - 匹配阈值：`0.7`
   - 勾选"初始化节点"
3. 点击"截图并框选"
   - 框选"区域"筛选按钮
   - 按Enter确认
4. 点击"保存节点"

#### 节点4：加载完了模板

1. 点击"新建节点"
2. 填写信息：
   - 名称：`加载完了`
   - 类型：`verify`
   - 模板图片：`loading_done.png`
   - 匹配阈值：`0.8`
   - **不要**勾选"初始化节点"
3. 点击"截图并框选"
   - 滚动到列表底部
   - 框选"加载完了"或"没有更多数据"文案
   - 按Enter确认
4. 点击"保存节点"

### 保存配置

点击顶部工具栏的"保存"按钮，配置会保存到 `config/nodes.json`。

## 第四步：配置区域列表

编辑 `config/regions.json`，根据实际情况修改区域列表：

```json
{
  "version": "1.0",
  "regions": [
    "黄浦区",
    "徐汇区",
    "长宁区",
    "静安区",
    "普陀区",
    "虹口区",
    "杨浦区"
  ]
}
```

## 第五步：运行自动化流程

```bash
# 确保大众点评小程序已打开到首页
python main.py
```

## 第六步：运行网页版详情补全

```bash
# 默认优先使用本机 Chrome/Chromium
./start_playright.sh
```

常用参数：

```bash
./start_playright.sh --limit 5
./start_playright.sh --browser-path "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

### 执行流程

系统会自动执行以下步骤：

1. ✓ 加载配置文件
2. ✓ 初始化核心组件
3. ✓ 启动Rust抓包工具（如果存在）
4. ✓ 执行初始化节点：
   - 点击"美食"按钮
   - 验证列表页加载
   - 点击"区域"筛选
5. ✓ 识别所有区域
6. ✓ 遍历每个区域：
   - 点击区域名称
   - 等待列表刷新
   - 开始滚动采集：
     - 向下滑动500像素
     - 等待0.5秒
     - 识别"加载完了"
     - 如果未完成，继续滑动
   - 切换到下一个区域
7. ✓ 完成所有区域采集

### 查看日志

日志文件保存在 `logs/automation_YYYY-MM-DD.log`

```bash
# 实时查看日志
tail -f logs/automation_$(date +%Y-%m-%d).log
```

## 常见问题

### Q1: 模板识别失败怎么办？

**A:** 
1. 检查模板图片是否清晰
2. 降低匹配阈值（0.85 → 0.7）
3. 重新截取模板图片
4. 清除坐标缓存：删除 `config/cache.json`

### Q2: 点击位置不准确怎么办？

**A:**
1. 清除缓存：删除 `config/cache.json`
2. 调整随机偏移范围：编辑 `config/settings.py`
   ```python
   RANDOMIZATION = {
       'click_offset_range': 3,  # 改为3像素
   }
   ```

### Q3: 滚动无法停止怎么办？

**A:**
1. 检查"加载完了"模板是否正确
2. 降低识别阈值：编辑 `config/nodes.json`
   ```json
   "scroll_config": {
       "loading_done_threshold": 0.7
   }
   ```
3. 查看日志确认识别情况

### Q4: 如何调试单个节点？

**A:**
创建测试脚本：

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
