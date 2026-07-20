# UI 还原工程指南：从 Figma 到 Flutter 100% 还原

> 本文档总结了 pantas-launcher 项目中多轮 UI 还原实践得出的方法论，
> 指导如何从 Figma 设计稿编写高还原度、符合业务规范的 Flutter 代码。

## 一、核心原则

### 1. 先读数据，再写代码

**永远不要对着截图猜布局。** Figma 的 `get_design_context` 返回的是结构化数据：
每个元素的精确坐标（left/top/width/height）、变换（rotate/scale）、颜色、字体、
素材 URL。这些是「图纸」，截图只是参考。

```
正确流程： get_design_context → 读坐标/颜色/变换 → 写代码 → 设备验证
错误流程： 看截图 → 猜位置 → 写代码 → 像素 diff → 改 → 再 diff → 再改…
```

### 2. UI / 显示数据 / 触发数据 三分离

公共组件不绑死业务语义。以方向键为例：

```dart
// 数据模型：描述「这个槽位显示什么、触发什么」
class PadKey {
  final GamepadKey key;       // 触发标识（up / a / l1… 任意）
  final String? svgAsset;     // 显示资源（注入，换皮肤用）
  final ImageProvider? icon;  // 备选显示资源（PNG）
  final String? label;        // 备选显示（文字）
}

// 组件：只管「按资源渲染 + 按回调触发」
class DPad extends StatelessWidget {
  final PadKey up, down, left, right;          // 4 个槽位
  final ValueChanged<GamepadKey> onPress;       // 触发（回传 key）
  final Set<GamepadKey> highlighted;            // 高亮（定位场景）
  final double opacity;                         // 收起态
}
```

- 组件不知道 `up` 还是 `a`，只按注入的 `svgAsset` 渲染
- 点击回传 `GamepadKey`，业务在上层处理
- 换皮肤 = 换 `svgAsset`，组件一行不动

### 3. 每个元素独立可替换

每个方向、每个按键用自己的独立资源文件，不靠 Transform 变换同一张图。
原因：换皮肤时新素材可能不是同形状的旋转，绑死变换会出错。

```
✅ btn_up.svg / btn_right.svg / btn_down.svg / btn_left.svg（4 个独立文件）
❌ btn_up.svg + Transform.rotate（1 张图 + 代码旋转）
```

## 二、操作流程

### Step 1：读 Figma 设计数据

```
get_design_context(nodeId)  → JSX 结构（坐标/颜色/变换/素材URL）
get_metadata(nodeId)        → 轻量结构（节点名/尺寸/子节点）
get_screenshot(nodeId)      → 截图（仅参考，不做像素对比基准）
```

需要提取的关键信息：
- **坐标**：每个子元素的 left/top/width/height
- **变换**：rotate、scale、translate（注意嵌套顺序）
- **颜色**：CSS 变量名 + fallback 值（如 `var(--fill-0, #6A7691)` → `#6A7691`）
- **素材**：每个 img 的 asset URL（下载后用 `file` 命令区分 SVG/PNG）
- **字体**：字重映射（Heavy → w900, Bold → w700, Regular → w400）

### Step 2：判断「能代码画的」vs「必须用图的」

| 类型 | 处理方式 | 例子 |
|------|---------|------|
| 几何/文字/渐变/卡片 | Flutter 原生 widget | Container、Text、BoxDecoration |
| 图标/Logo（矢量） | SVG 素材 + flutter_svg | 方向键臂、品牌图标 |
| 插画/产品图（栅格） | PNG 素材 + Image.asset | 场景背景、主机产品图 |

### Step 3：下载和处理素材

```bash
# 下载 SVG/PNG
curl -o asset.svg "https://www.figma.com/api/mcp/asset/<uuid>"

# 区分格式（Figma 导出的 SVG 常被命名为 .png）
file asset.png  # 实际可能是 SVG

# SVG → 高清 PNG（如需栅格化）
rsvg-convert -z 8 asset.svg -o asset.png

# 压缩过大的 PNG（避免几 MB 的 logo）
python3 -c "from PIL import Image; Image.open('big.png').resize((200,h),Image.LANCZOS).save('small.png')"
```

### Step 4：处理 SVG 特殊语法

Figma 导出的 SVG 常含 flutter_svg 不支持的特性：

| SVG 特性 | flutter_svg 支持 | 处理方式 |
|----------|----------------|---------|
| CSS 变量 `var(--x, #color)` | ❌ | 替换为纯色 fallback 值 |
| `<mask>` | △ 部分支持，渲染异常 | 去掉 mask，改用 `stroke` 属性 |
| `preserveAspectRatio="none"` | ❌ | 默认 `meet` 即可（如宽高比一致） |
| `overflow="visible"` | ❌ | 删除（路径已在 viewBox 内时不影响） |

```bash
# 批量清理 SVG 中的 CSS 变量
sed -i '' 's/var(--[^,]*, \([^)]*\))/\1/g' asset.svg
```

### Step 5：编写组件代码

**固定画布 + FittedBox**（适用于横屏/竖屏固定比例的设计）：

```dart
Scaffold(
  body: Center(
    child: FittedBox(
      fit: BoxFit.contain,
      child: SizedBox(
        width: 390,   // Figma 帧宽
        height: 844,  // Figma 帧高
        child: Canvas(),  // 内部用 Figma 坐标 1:1 摆放
      ),
    ),
  ),
)
```

**Stack + Positioned**（固定坐标设计用绝对定位最忠实）：

```dart
Stack(children: [
  // 背景层
  _Background(),
  // 按坐标直接摆（从 get_design_context 读的值）
  Positioned(left: 45, top: 484, child: DPad(...)),
  Positioned(left: 219, top: 484, child: ABXY(...)),
  ...
])
```

**背景图裁剪**（Figma 的 image 常带裁剪因子）：

```dart
// Figma: left -0.03%, top -21.79%, w 100.05%, h 121.79%
Positioned(
  left: W * -0.0003,
  top: H * -0.2179,
  width: W * 1.0005,
  height: H * 1.2179,
  child: Image.asset('bg.png', fit: BoxFit.fill),
)
```

### Step 6：设备验证（不用 Figma 截图做像素 diff）

**为什么不用像素 diff**：Flutter 和 Figma 是不同渲染引擎，同一个 SVG/路径/字体，
光栅化出来的像素天然不同。像素匹配率在 60-98% 之间波动，但**不代表还原度**。

**正确验证**：

1. **坐标确认**：代码里的 left/top/width/height 是否和 `get_design_context` 读到的一致
2. **设备截图采样**：在模拟器上截图，采样关键点颜色值，确认元素在正确位置渲染
3. **视觉验收**：在设备上看整体效果，人眼判断「对不对」
4. **比例测量**：测量元素占屏幕的比例，和设计帧里的比例对比

```python
# 测量元素占屏幕比例
design_width = 390
element_design_width = 126
expected_ratio = element_design_width / design_width  # 32.3%

# 设备截图测量
device_screenshot_width = 1179
element_device_width = 380  # 截图里量出来的
actual_ratio = element_device_width / device_screenshot_width  # 32.2%
# 32.2% ≈ 32.3% → 比例一致
```

## 三、字体处理

### iOS 不指定 fontFamily

```dart
// ❌ 显式指定会导致 Flutter 找不到 bundled 字体 → fallback 到非 PingFang
Text('文字', style: TextStyle(fontFamily: 'PingFang SC'))

// ✅ 不指定，iOS 系统自动用 PingFang（中文）/ SF（西文）
Text('文字', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500))
```

### 打包自定义字体（Android / 测试环境）

```yaml
# pubspec.yaml
fonts:
  - family: AlibabaPuHuiTi
    fonts:
      - asset: fonts/Regular.otf
        weight: 400
      - asset: fonts/Bold.otf
        weight: 700
```

```dart
// Text style 里指定（仅 Android/测试需要，iOS 系统自动）
TextStyle(fontFamily: 'AlibabaPuHuiTi', fontWeight: FontWeight.w700)
```

### Golden test 加载字体

`flutter test` 环境没有系统字体，需用 `FontLoader` 显式注册：

```dart
Future<void> main() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  final ByteData data = await rootBundle.load('fonts/Heavy.otf');
  final FontLoader loader = FontLoader('AlibabaPuHuiTi')
    ..addFont(Future.value(data));
  await loader.load();
  // ... tests
}
```

## 四、常见陷阱

### 1. SVG mask 导致渲染异常

**现象**：flutter_svg 渲染 Figma 导出的 SVG 时，部分区域变成黑色块。

**根因**：Figma 用 `<mask>` 创建内描边效果，flutter_svg 对 mask 支持不完整。

**解决**：去掉 mask，改用 `stroke` 属性。视觉差异极小（内描边 vs 居中描边，差 0.75px）。

### 2. 图片在 Golden test 不渲染

**现象**：`Image.asset` 在 `flutter test` 里空白。

**根因**：图片异步解码，测试环境的 fake clock 不推进真实时间。

**解决**：`tester.runAsync(() => precacheImage(...))`。

### 3. Transform.rotate 方向混淆

**现象**：旋转后元素位置偏移或方向错误。

**根因**：Flutter `canvas.rotate` 正角 = CW（顺时针）；CSS `rotate-90` = CW；
但嵌套 transform 的顺序（内外层）决定了最终效果。

**解决**：用 SVG 内嵌 `<g transform>` 替代 Flutter Transform，让 SVG 渲染器
统一处理变换，避免 Flutter/Canvas 层面的方向歧义。

### 4. 像素 diff 误导

**现象**：Golden test 渲染图和 Figma 截图对比，匹配率只有 60-70%。

**根因**：Flutter（Skia/Impeller）和 Figma 是不同渲染引擎，同一个 SVG 路径
光栅化的像素天然不同。60% 不代表「还原度 60%」。

**解决**：不要用 Figma 截图做像素 diff 基准。用设备截图 + 坐标/比例测量来验证。

