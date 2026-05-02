# 点评网页版详情抓取方案

## 1. 目标

当前系统保留 App 侧抓包能力，继续通过手机端抓取点评列表接口；商家详情不再依赖 App 内逐条点击，而是改为基于 Playwright 打开点评网页版详情页，通过 `shopUuid` 直接访问详情地址并补全结构化数据。

主入口地址：

```text
https://www.dianping.com/shop/<shopUuid>
```

示例：

```text
https://www.dianping.com/shop/G7lZQSVUguP43EIT
```

## 2. 整体链路

### 2.1 列表阶段

1. 手机端继续跑自动化和抓包。
2. 命中点评列表接口 `/wxmapi/wxsearch/search`。
3. 将列表响应导入 `dianping_shop` 数据集。
4. 每条记录至少保留这些字段：
   - `shop_id`
   - `shop_uuid`
   - `name`
   - `district`
   - `rating`
   - `avg_price`

说明：

- 后续网页详情抓取的关键主键是 `shop_uuid`。
- 如果当前 `shop_list` 协议未导入 `shop_uuid`，则后续实现 Playwright 时要先补这个字段。

### 2.2 详情补全阶段

1. 从 `dianping_shop` 中筛选有 `shop_uuid` 且未补全详情的记录。
2. Playwright 复用本地浏览器登录态。
3. 按 `https://www.dianping.com/shop/<shopUuid>` 打开详情页。
4. 关闭干扰弹层。
5. 等待详情页关键节点出现。
6. 提取详情字段。
7. 将结果合并写回 `dianping_shop`。

## 3. 页面流程

### 3.1 浏览器启动

推荐使用持久化上下文：

- 保留 Cookie 和登录态
- 避免每次都扫码登录
- 后续可单独维护浏览器用户目录

建议：

- 首次运行允许人工扫码或登录
- 后续直接复用 session

### 3.2 登录判断

打开首页或详情页后，先判断是否未登录。

未登录参考节点：

```html
<a rel="nofollow" class="item " href="//account.dianping.com/login" data-click-name="login">你好，请登录/注册</a>
```

处理逻辑：

1. 如果检测到登录入口，点击进入登录页。
2. 等待用户手动登录完成。
3. 登录完成后，原登录入口应消失。
4. 登录成功后再继续访问目标详情页。

登录完成判定：

- 原“你好，请登录/注册”节点消失
- 或页面出现用户头像、用户菜单、登录后导航节点

### 3.3 打开目标详情页

目标地址：

```text
https://www.dianping.com/shop/<shopUuid>
```

例如：

```text
https://www.dianping.com/shop/l8HxKTJa1L21pETO
```

实现要求：

- 每个商家建议单独打开新标签页，完成后关闭
- 或者单页串行访问并等待页面完全切换
- v1 推荐串行处理，便于排查风控和失败原因

### 3.4 页面稳定判定

到达详情页后，不能只靠 URL 变化判断成功，必须至少满足下列任一条件：

- 电话节点存在
- 地址节点存在
- 商户名主标题存在
- 主内容容器存在

可作为成功参考的电话节点：

```html
<div data-launch-name="telephone" data-launch-bid="b_i7ojv4l3" data-launch-shop-id="67462688" data-launch-shop-uuid="l8HxKTJa1L21pETO" data-launch-shop-type="10" data-launch-shop-category-id="34246" data-launch-city-id="7" class="desc-phone wx-view" data-inited="true"></div>
```

## 4. 弹层与异常处理

### 4.1 打开 App 弹层

网页详情页可能弹出“移步至大众点评 App”的遮罩，必须优先处理。

参考结构：

```html
<div class="oap-wide" id="oapWide" style="display: block;">
  <div class="oap-text">移步至大众点评App</div>
  <div class="oap-text">查看/使用更多内容</div>
  <div class="oap-qrcode-wrap">
    <div class="oap-qrcode-img-wrap"></div>
    <div id="openAppLaunchModalPCQrCodeDraw"><canvas width="176" height="176"></canvas></div>
  </div>
  <div class="oap-close"></div>
</div>
```

处理逻辑：

1. 如果存在 `#oapWide` 或 `.oap-wide`，先判断是否可见。
2. 如果可见，点击 `.oap-close`。
3. 等待弹层消失。
4. 如果关闭失败，记录 `blocked`，不要无限重试。

### 4.2 店铺不存在

可能出现：

- 无效 `shopUuid`
- 页面跳转到错误页
- 返回空白页或 404 提示

处理结果：

- 标记 `detail_fetch_status = not_found`
- 保留 `shop_uuid` 和 `shop_url`
- 跳过当前记录，继续下一条

### 4.3 风控或验证页面

可能出现：

- 滑块验证
- 人机验证
- 登录态异常
- 访问频率过高被限制

处理结果：

- 标记 `detail_fetch_status = blocked`
- 保存失败时间和错误摘要
- 停止当前批次或暂停等待人工处理
- 不做无限循环自动重试

### 4.4 页面加载超时

如果在指定超时内未出现关键节点：

- 标记 `detail_fetch_status = timeout`
- 记录 `shop_uuid`
- 可进入有限次数重试，例如 1 到 2 次

## 5. 结构化字段输出

网页详情抓取阶段统一回写 `dianping_shop`。

### 5.1 基础字段

- `shop_uuid`
- `shop_url`
- `detail_fetch_status`
- `detail_fetch_time`

### 5.2 优先补全字段

- `phone`
- `address`
- `open_time`
- `category`
- `district`
- `shop_notice`

### 5.3 可选扩展字段

- `merchant_tags`
- `photo_count`
- `has_phone`
- `raw_html_excerpt`

字段说明：

- `has_phone`
  - 有电话节点或解析出电话时为 `true`
  - 页面正常但没有电话时为 `false`
- `detail_fetch_status`
  - `success`
  - `no_phone`
  - `not_found`
  - `blocked`
  - `timeout`

## 6. 数据合并策略

### 6.1 合并原则

列表字段来自 App 抓包，详情字段来自网页补全。

默认策略：

1. 列表已有字段保留。
2. 网页详情只补空值或新增字段。
3. 不轻易覆盖列表阶段已经更可信的字段。

### 6.2 唯一键

推荐使用：

```text
shop_uuid
```

如果部分历史数据没有 `shop_uuid`，则临时回退：

```text
shop_id
```

但后续长期方案仍应以 `shop_uuid` 为主。

## 7. 与现有系统的衔接

### 7.1 输入

来自当前系统的结构化列表数据：

- 数据集：`dianping_shop`
- 来源协议：`config/meituan/shop_list.json`

### 7.2 输出

继续写回：

- 数据集：`dianping_shop`
- 存储方式：SQLite
- 导出方式：Excel

### 7.3 执行时机

v1 建议使用手动触发：

1. 先抓取列表
2. 再点击“详情补全”
3. 批量跑 Playwright 详情抓取

原因：

- 便于隔离 App 抓包和网页访问问题
- 便于观察登录态、风控和失败记录
- 便于后续支持断点续跑

## 8. 反爬与约束

### 8.1 不混用手机代理链路

网页详情抓取不依赖：

- ADB
- 手机代理
- 抓包 CA

它是独立于手机抓包配置的一条补全链路。

### 8.2 登录态要求

Playwright 方案默认要求具备有效的点评网页版登录态。

建议：

- 首次人工登录
- 登录态持久化到本地目录
- 后续自动复用

### 8.3 限流建议

为了降低风控风险：

- 串行处理商家
- 访问间隔加随机等待
- 单批数量不要过大
- 遇到 `blocked` 时立即暂停

## 9. 后续实现建议

后续正式编码时建议拆成三个部分：

### 9.1 Playwright 访问器

负责：

- 启动浏览器
- 复用 session
- 打开详情页
- 关闭弹层
- 检测页面状态

### 9.2 详情解析器

负责：

- 从页面 DOM 提取字段
- 标准化输出结构
- 返回状态码和错误原因

### 9.3 数据回写器

负责：

- 根据 `shop_uuid` 查找原记录
- 合并详情字段
- 更新 SQLite
- 供 Excel 导出直接使用

## 10. 验收场景

1. 已有 `shop_uuid` 的商家可直接打开详情页并补全数据。
2. 未登录时可进入登录流程，登录后继续抓取。
3. 遇到“打开 App”弹层时可关闭并继续执行。
4. 商家没有电话时可正常完成并标记 `has_phone = false`。
5. 无效 `shop_uuid` 会被标记为 `not_found`。
6. 风控页或验证码会被标记为 `blocked`，不会无限重试。
7. 详情补全完成后，结果可继续导出到 Excel。
