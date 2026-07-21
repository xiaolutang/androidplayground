---
name: figma-ui-impl
description: 从 Figma 设计稿还原 Flutter UI。触发——用户给 figma.com 链接、说"还原/实现这个 UI"、"from Figma"、"照着设计做"。按固定流程执行：读设计数据 → 下载素材 → 三分离组件 → 布局 → 设备验证。
---

收到 Figma 链接或"还原 UI"请求时，严格按以下步骤执行。**核心：数据驱动，不靠截图猜布局。**

## Step 0：先理解页面和状态
- 先列出页面的 z 层：底层内容、蒙层、浮层、始终置顶的触发器分别是谁
- 识别同一页面的状态机（正常态 / 菜单态 / 收起态等），逐项记录状态差异
- 明确触发、关闭、焦点移动和激活方式；不要把一个状态误做成独立页面
- 产出一张“层级 + 状态 + 交互”清单，再开始提取单个元素

## Step 1：读设计数据
- 从 Figma URL 提取 `fileKey` 和 `node-id`（`node-id=XXXX-YYYY` → `XXXX:YYYY`）
- 调 `get_design_context(nodeId)` + `get_metadata(nodeId)`
- 从返回里提取每个元素的：`left/top/width/height`、变换(rotate/scale)、颜色（`var(--x,#c)` 取 `#c`）、字重（Heavy→w900, Bold→w700）、素材 URL
- 产出：一份元素清单（坐标+样式），作为后续编码的"图纸"

## Step 2：判断渲染方式 + 下载素材
按元素类型分流：
- **几何/文字/卡片/渐变** → Flutter 原生（Container/Text/BoxDecoration）
- **矢量图标/Logo** → `download_assets(nodeId, defaultFormat="svg")`，从节点 SVG 提取图标 path（去掉背景 rect、替换 CSS 变量为纯色）
- **栅格插画/产品图** → PNG（`download_assets`）

⚠️ **决策点（最易踩坑）**：如果图标内容不对，**别用** design_context 里的单个素材 URL（`imgVector`/`imgBtn` 等，Figma 组件复用时指向通用资源，易下错）—— 用 `download_assets(svg)` 拿节点完整 SVG，提取真实 path。

## Step 3：三分离组件（规格注入）
- **规格模型**：把「显示 + 行为」打包，组件不绑业务
  ```dart
  class UiSpec {
    final String? svgAsset;       // 显示：矢量图
    final ImageProvider? icon;    // 显示：位图
    final String? label;          // 显示：文字
    final VoidCallback? onTap;    // 行为
  }
  ```
- **组件**：只渲染规格 + 触发回调，按**视觉结构**命名（`IconTile`/`DiamondGrid`/`CapsuleRow`），不绑业务（不叫"ABXY"/"登录按钮"）
- **页面层组装**：构造 `UiSpec` 注入资源+回调，传给组件
- 容器组件封装子组件相对布局（坐标封装在内）
- 重复卡片必须复用同一个公共 widget；显示、行为、初始焦点和特殊状态全部由数据配置
- 焦点环、选中框、hover 等状态视觉抽成公共组件，由真实 Focus/状态系统驱动

## Step 4：布局
```dart
Scaffold(body: Center(child: FittedBox(
  fit: BoxFit.contain,
  child: SizedBox(width: <Figma帧宽>, height: <Figma帧高>, child: Stack([
    Positioned(left: .., top: .., child: ..),  // Figma 坐标 1:1
  ])),
)))
```
- 背景图裁剪：Figma image 带裁剪因子时用 `OverflowBox` + `Transform` 精确还原
- 重复元素用 `ListView` / `GridView` 等真实集合布局；顺序和数量来自数据，禁止手写固定行列分支冒充数据驱动
- 焦点态允许超出普通单元时，普通 Grid 只负责 slot，焦点 wrapper 在 slot 内用 `Stack(clipBehavior: Clip.none)` 精确外扩

## Step 5：设备验证（数据优先，图片最少用）
1. **坐标确认**：代码 left/top/width/height == Figma 数据（用 get_metadata 文本对照，不靠图）
2. **代码忠实度**：SVG path 直接取自 Figma、颜色/字体逐项对
3. **编译/渲染**：`flutter analyze` + golden test 通过
4. **视觉（最后一步，整体一次）**：仅当以上都过后，截**一张整体图**确认观感；看不了图就交给用户验收，**不反复 analyze 局部**（视觉模型易误判，且低效）
- golden 必须渲染真实页面组合态，不能在测试里重复添加组件内部已有的定位/裁剪容器
- golden 中使用项目真实字体；出现方块字时测试无效，不能更新为基准
- **禁止**用 Figma 截图做像素 diff 基准
- **禁止**反复 analyze 局部截图代替数据对照 —— 找差异优先用 get_metadata 坐标/尺寸，图片只做整体观感最后确认

## 决策点：常见坑速查
| 现象 | 根因 | 解决 |
|---|---|---|
| 图标内容不符 | 用了单个素材 URL | `download_assets(svg)` 拿节点完整 path |
| 点 A 触发 B | `Transform.rotate` 后命中区偏移 | 能不旋转就不；必须旋转则行为按视觉补偿 |
| SVG 渲染黑块 | `<mask>` 支持不完整 | 去 mask 改 `stroke` |
| PNG 圆外白底 | 默认不透明背景 | 优先 SVG；PNG 处理 alpha |
| iOS 字体变丑 | 指定 fontFamily 找不到 bundled | iOS 不指定（系统字）；Android 打包 |
| 描边浓淡不一 | `fill-opacity` 只染 fill | 用 `opacity`（整体，含 stroke） |

## 产出
- Flutter 组件代码（三分离）+ 页面组装
- 设备验证截图
