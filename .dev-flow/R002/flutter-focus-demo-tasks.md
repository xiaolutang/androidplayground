---
version: "1.0"
type: tasks
topic: flutter-focus-demo
requirement_cycle: R002
workflow:
  evaluate_provider: local
  mode: auto
status: planned
---

# Flutter 焦点进阶 Demo — 前端任务清单

基于 [design_frontend.md](analysis/2026-06-26--flutter-focus-demo-frontend.md) 设计，拆解为 4 个功能任务 + 3 个测试任务（单元/widget/集成）。

## 全局约束

- **状态管理使用 `setState`**，不引入 Provider / Bloc / Riverpod（demo 单页面，`setState` 足够；框架选择影响 architecture.md INV-1 未锁定项，不在本 demo 范围）
- **不引入任何第三方依赖**（纯用 Flutter SDK 内置 Focus 系统；唯一例外是 Flutter 官方 `integration_test` 包——属于 Flutter 生态一等公民，不计入"第三方依赖"约束）
- **不修改 Add-to-App 宿主配置**（`app/`、`.ohos/`、iOS/Android 原生配置不动，demo 独立 `flutter run` 运行）
- **测试策略：三层自动化测试覆盖**（对齐 design 暂不实现项中的"Widget 测试自动化"——本批补齐）
  - 单元测试（R002-FF005）：覆盖 `SmartFocusTraversalPolicy` 三层降级纯逻辑的每条分支
  - Widget 测试（R002-FF006）：覆盖 `FocusableButton` 高亮切换 + enabled=false + dispose 安全
  - 集成测试（R002-FB007）：用 `integration_test` 包自动化跑三场景 A/B/C，断言 `primaryFocus.debugLabel`
- **测试命令**：`flutter test`（单元 + widget）、`flutter test integration_test/`（集成）
- **design 暂不实现项遵循**：状态管理框架、TV 遥控器映射、MethodChannel、多级 FocusScope 嵌套测试、真实业务数据、焦点动画过渡——均不在本批任务范围

## 执行顺序

1. ✅ R002-FF003 — SmartFocusTraversalPolicy 策略引擎（无依赖，核心先行）
2. ✅ R002-FF004 — FocusableButton 可聚焦按钮（无依赖，可与 FF003 并行）
3. ⬜ R002-FB006 — FocusDebugOverlay 调试浮层（无依赖，可与 FF003/FF004 并行）
4. ⬜ R002-FF005 — SmartFocusTraversalPolicy 单元测试（依赖 FF003，验证三层降级 5 条分支）
5. ⬜ R002-FF006 — FocusableButton widget 测试（依赖 FF004，验证高亮 + enabled + dispose）
6. ⬜ R002-FB005 — PersonalCenterDemoPage 页面组装 + main.dart 入口改造（依赖 FF003 + FF004 + FB006）
7. ⬜ R002-FB007 — 焦点 demo 三场景集成测试（依赖 FB005 + FF005 + FF006，自动化验证 A/B/C）
8. ⬜ 最后 — 编译验证 + `flutter test` 全量 + 三场景手动验证（依赖 FB007）

---

## R002-FF003：smart_focus_policy.dart — SmartFocusTraversalPolicy 策略引擎 `✅ 已完成`

- 文件：`flutter_logic/lib/focus/smart_focus_policy.dart`
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 5（最高，核心引擎）
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `SmartFocusTraversalPolicy` 继承 `FocusTraversalPolicy`，可被 `FocusTraversalGroup.policy` 接受
  - `_smartRequestFocus` 严格按"记忆 → 优先级 → 物理兜底"顺序降级，每层命中即返回不再继续
  - 记忆层检查 `targetScope.focusedChild != null && focusedChild.canRequestFocus`，两者都满足才命中
  - 优先级层委托 `OrderedTraversalPolicy().findFirstFocus(targetScope)`，返回 null 或等于 targetScope 时降级
  - 物理兜底层 `_findFirstFocusableChild` 递归 DFS，跳过 `canRequestFocus=false` 的节点
  - 三层全未命中时，`targetScope.requestFocus()` 自身兜底（避免 primaryFocus=null）
  - `findFirstFocus` 和 `inDirection` 正确委托到 `_smartRequestFocus`
  - `resetMemory(scope)` 能清空指定 scope 的记忆（`scope.focusedChild?.unfocus()`）
  - `flutter analyze` 无 error
- test_tasks:
  - type: integration
    description: 三层降级策略手动验证（通过 FB005 页面 + FB006 调试浮层）
    scenarios:
      - 场景 A 首次进入：按右键进右侧内容区，焦点落在 NumericFocusOrder(1.0) 而非顶部装饰
      - 场景 B 跨区域记忆：切走再回来，焦点回到上次位置而非重新走优先级
      - 场景 C 删除节点兜底：删除当前焦点后按方向键，焦点落到邻近可用节点不丢失
- contract_refs: []
- decision_refs: [D2, D3, D4, D5]
- blocked_files: [`flutter_logic/pubspec.yaml`]

### FF003.1 类骨架与继承 `⬜`

新建 `flutter_logic/lib/focus/smart_focus_policy.dart`，定义 `SmartFocusTraversalPolicy extends FocusTraversalPolicy`。

```dart
import 'package:flutter/widgets.dart';

/// 自定义焦点遍历策略：记忆 > 优先级 > 物理兜底三层降级。
///
/// 挂在 FocusTraversalGroup.policy 上，方向键触发时被 Flutter 焦点系统回调。
class SmartFocusTraversalPolicy extends FocusTraversalPolicy {
  // 内部复用一个 OrderedTraversalPolicy 实例做优先级层委托
  final OrderedTraversalPolicy _orderedPolicy = OrderedTraversalPolicy();

  // ... 方法见 FF003.2 / FF003.3
}
```

### FF003.2 核心三层降级逻辑 _smartRequestFocus `⬜`

实现三层降级决策。**这是整个 demo 的命脉**，每层的命中/未命中判断必须严谨。

```dart
/// 三层降级：记忆 → 优先级 → 物理兜底。命中即返回 true。
bool _smartRequestFocus(FocusScopeNode targetScope) {
  // 1. 记忆层：scope 自动记住的上次焦点子节点
  final FocusNode? remembered = targetScope.focusedChild;
  if (remembered != null && remembered.canRequestFocus) {
    remembered.requestFocus();
    return true;
  }

  // 2. 优先级层：委托 OrderedTraversalPolicy 找 NumericFocusOrder 最小节点
  final FocusNode? priorityFirst = _orderedPolicy.findFirstFocus(targetScope);
  if (priorityFirst != null && priorityFirst != targetScope) {
    priorityFirst.requestFocus();
    return true;
  }

  // 3. 物理兜底层：DFS 递归找第一个可聚焦子节点
  final FocusNode? fallback = _findFirstFocusableChild(targetScope);
  if (fallback != null) {
    fallback.requestFocus();
    return true;
  }

  // 4. 极端兜底：scope 自身持有焦点
  targetScope.requestFocus();
  return true;
}
```

### FF003.3 DFS 兜底搜索 _findFirstFocusableChild `⬜`

递归深度优先搜索，跳过 `canRequestFocus=false` 的节点（含已 dispose 的节点）。

```dart
/// DFS 递归找第一个 canRequestFocus=true 的后代节点。
FocusNode? _findFirstFocusableChild(FocusNode node) {
  for (final child in node.children) {
    if (child.canRequestFocus) {
      return child;
    }
    final FocusNode? descendant = _findFirstFocusableChild(child);
    if (descendant != null) {
      return descendant;
    }
  }
  return null;
}
```

### FF003.4 重写 FocusTraversalPolicy 回调入口 `⬜`

SmartFocusTraversalPolicy 的核心设计：**只重写"进入 scope 时的初始焦点选择"**（`findFirstFocus`），scope 内部的方向键移动委托给 `OrderedTraversalPolicy`。

**Flutter 焦点系统的工作方式**：
- 当用户按方向键跨 `FocusTraversalGroup` 边界时（如左导航 → 右内容区），Flutter 框架自动定位目标 group，调用其 policy 的 `findFirstFocus`
- 因此 `findFirstFocus` 是三层降级的唯一入口
- `inDirection` 只负责同一 group 内部的方向键移动（如右内容区的上下键），委托给 `_orderedPolicy` 即可

```dart
/// 跨 group 进入时的入口：三层降级决策
@override
FocusNode? findFirstFocus(FocusNode currentNode, {bool ignoreCurrentFocus = false}) {
  final FocusScopeNode? scope = currentNode.nearestScope;
  if (scope == null) return null;
  _smartRequestFocus(scope);  // FF003.2 的三层降级
  return FocusManager.instance.primaryFocus;
}

/// scope 内部方向键移动：委托 OrderedTraversalPolicy（走 FocusTraversalOrder 顺序）
@override
bool inDirection(FocusNode currentNode, TraversalDirection direction) {
  return _orderedPolicy.inDirection(currentNode, direction);
}

/// findNext / findPrevious / findLast 均委托给 _orderedPolicy
@override
FocusNode? findNextFocus(FocusNode currentNode, TraversalDirection direction) {
  return _orderedPolicy.findNextFocus(currentNode, direction);
}

@override
FocusNode? findPreviousFocus(FocusNode currentNode, TraversalDirection direction) {
  return _orderedPolicy.findPreviousFocus(currentNode, direction);
}

@override
FocusNode? findLastFocus(FocusNode currentNode) {
  return _orderedPolicy.findLastFocus(currentNode);
}
```

> **设计澄清**（B2 审查点）：
> - `findFirstFocus` 是三层降级的**唯一触发点**。Flutter 框架在跨 `FocusTraversalGroup` 边界时（水平方向键）自动调用目标 group 的 `findFirstFocus`，因此**不需要**在 `inDirection` 中手动处理跨 scope 逻辑。
> - `inDirection` / `findNextFocus` / `findPreviousFocus` 委托给 `_orderedPolicy`，保证同一 group 内部的垂直移动（上下键）走 `NumericFocusOrder` 顺序。
> - **Fallback 方案**：若验证阶段发现跨 group 时 `findFirstFocus` 未被框架调用（Flutter 版本差异），在 `inDirection` 中检测水平方向且 `_orderedPolicy.findNextFocus` 返回 null 时，手动定位相邻 group 并调用 `_smartRequestFocus`。先用上述简化方案，FB005 验证阶段确认框架行为。

### FF003.5 调试用 resetMemory `⬜`

```dart
/// 清空指定 scope 的记忆（调试浮层"重置记忆"按钮触发）。
void resetMemory(FocusScopeNode scope) {
  scope.focusedChild?.unfocus();
}
```

---

## R002-FF004：focusable_button.dart — FocusableButton 可聚焦按钮 `✅ 已完成`

- 文件：`flutter_logic/lib/focus/focusable_button.dart`
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `FocusableButton` 是 `StatefulWidget`，接收 `label` / `order` / `onTap` / `enabled` 参数
  - 内部创建 `FocusNode(debugLabel: label)` 并在 `dispose` 时释放
  - 获得焦点时显示边框（如蓝色 2px）+ 1.05 倍 `Transform.scale`
  - 失去焦点时恢复无边框 + 1.0 倍缩放
  - 若传入 `order`，用 `FocusTraversalOrder` 包裹以支持优先级标记
  - 点击或回车键触发 `onTap` 回调
  - `flutter analyze` 无 error
- test_tasks:
  - type: integration
    description: 按钮焦点高亮可视化验证
    scenarios:
      - 获得焦点的按钮显示边框+缩放，肉眼可辨
      - 失去焦点后样式恢复
      - enabled=false 的按钮不可获得焦点（方向键自动跳过，canRequestFocus=false）
      - 按钮从树中移除后 FocusNode 正确 dispose（场景 3 删除验证，无 use-after-dispose 崩溃）
- contract_refs: []
- decision_refs: [D6]
- blocked_files: []

### FF004.1 StatefulWidget 骨架与 FocusNode 生命周期 `⬜`

```dart
import 'package:flutter/material.dart';

class FocusableButton extends StatefulWidget {
  final String label;
  final FocusOrder? order;
  final VoidCallback? onTap;
  final bool enabled;

  const FocusableButton({
    super.key,
    required this.label,
    this.order,
    this.onTap,
    this.enabled = true,
  });

  @override
  State<FocusableButton> createState() => _FocusableButtonState();
}

class _FocusableButtonState extends State<FocusableButton> {
  late final FocusNode _focusNode;

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode(debugLabel: widget.label);
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }
  // build 见 FF004.2
}
```

### FF004.2 焦点高亮样式切换 `⬜`

用 `Focus` widget 的 builder 回调读 `hasFocus`，根据状态切换 `Container.decorations` 和 `Transform.scale`。

```dart
@override
Widget build(BuildContext context) {
  Widget button = Focus(
    focusNode: _focusNode,
    onPressed: widget.onTap, // 回车键触发
    child: Builder(
      builder: (context) {
        final bool focused = Focus.of(context).hasFocus;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          transformAlignment: Alignment.center,
          // 关键：focused 时边框 + 缩放，否则无边框
          // 用 Transform.scale 或 transform 矩阵实现 1.05 倍
          // child: 内部放 Text(widget.label) + InkWell（点击触发 onTap）
        );
      },
    ),
  );

  // 若传入 order，用 FocusTraversalOrder 包裹
  if (widget.order != null) {
    return FocusTraversalOrder(order: widget.order!, child: button);
  }
  return button;
}
```

> **实现提示**：`AnimatedContainer` 的 `transform` 字段接受 `Matrix4`，可用 `Matrix4.diagonal3Values(1.05, 1.05, 1.0)` 实现缩放。或更简洁地用 `Transform.scale(scale: focused ? 1.05 : 1.0)` 包裹 `Container`。边框用 `Container.decoration: BoxDecoration(border: focused ? Border.all(...) : null)`。

---

## R002-FB006：focus_debug_overlay.dart — FocusDebugOverlay 调试浮层 `⬜ 待处理`

- 文件：`flutter_logic/lib/debug/focus_debug_overlay.dart`
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: []
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `FocusDebugOverlay` 是 `StatelessWidget`，接收三个回调 `onDeleteCurrentFocus` / `onResetMemory` / `onPrintRect`
  - 实时显示 `FocusManager.instance.primaryFocus?.debugLabel`（用 `Builder` + `FocusManager.instance.addListener` 或简化为点击刷新）
  - 三个调试按钮（"删除当前焦点" / "重置记忆" / "打印 Rect"）分别触发对应回调
  - 调试按钮自身 `canRequestFocus: false`（用 `Focus(canRequestFocus: false)` 包裹），不抢焦点
  - 浮层视觉不遮挡内容区焦点高亮（位于底部或角落）
  - `flutter analyze` 无 error
- test_tasks:
  - type: integration
    description: 调试浮层功能验证
    scenarios:
      - primaryFocus.debugLabel 实时更新（切换焦点后显示变化）
      - "删除当前焦点"按钮触发页面移除当前焦点节点
      - "重置记忆"按钮清空 scope 记忆后，再次按右键重新走优先级层
- contract_refs: []
- decision_refs: [D7]
- blocked_files: []

### FB006.1 StatelessWidget 骨架与回调定义 `⬜`

```dart
import 'package:flutter/material.dart';

class FocusDebugOverlay extends StatelessWidget {
  final VoidCallback onDeleteCurrentFocus;
  final VoidCallback onResetMemory;
  final VoidCallback onPrintRect;

  const FocusDebugOverlay({
    super.key,
    required this.onDeleteCurrentFocus,
    required this.onResetMemory,
    required this.onPrintRect,
  });

  @override
  Widget build(BuildContext context) {
    // 见 FB006.2
  }
}
```

### FB006.2 primaryFocus 显示 + 三调试按钮 `⬜`

显示当前焦点状态 + 三个调试动作。**调试按钮自身不抢焦点**是关键约束。

```dart
@override
Widget build(BuildContext context) {
  return Focus(
    canRequestFocus: false, // 关键：整个浮层不抢焦点
    child: Container(
      // 位于底部，半透明背景
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // primaryFocus 显示：用 Builder + FocusManager.instance
          // 简化方案：Text('Focus: ${FocusManager.instance.primaryFocus?.debugLabel ?? 'null'}')
          // 注意：StatelessWidget 无法自动刷新，需用 StatefulBuilder 或让父页面 setState 传值
          // 推荐方案：改为接收 primaryFocusLabel 字符串参数，由父页面 FB005 管理
          Text('Focus: ...', style: const TextStyle(color: Colors.white, fontSize: 12)),
          const SizedBox(height: 4),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              _debugButton('删除当前焦点', onDeleteCurrentFocus),
              _debugButton('重置记忆', onResetMemory),
              _debugButton('打印 Rect', onPrintRect),
            ],
          ),
        ],
      ),
    ),
  );
}

Widget _debugButton(String label, VoidCallback onTap) {
  // 用 Focus(canRequestFocus: false) 包裹，避免调试按钮抢焦点
}
```

> **实现提示**：`primaryFocus` 实时刷新有两种方案：
> 1. **简化方案**（推荐 demo）：`FocusDebugOverlay` 改为接收 `String primaryFocusLabel` 参数，由父页面 `FB005` 用 `setState` + `FocusManager.instance.addListener` 管理并传入。
> 2. **自管理方案**：改为 `StatefulWidget`，内部 `initState` 注册 `FocusManager.instance.addListener`，`dispose` 时移除。
> 方案 1 更符合 design 的"FB006 是 StatelessWidget"定义，且父页面已经需要管理其他状态。

---

## R002-FF005：smart_focus_policy_test.dart — SmartFocusTraversalPolicy 单元测试 `⬜ 待处理`

> 测试目标：FF003 SmartFocusTraversalPolicy。本任务不新增功能节点，仅验证 FF003 的三层降级逻辑。

- 文件：`flutter_logic/test/focus/smart_focus_policy_test.dart`
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: [R002-FF003]
- priority: 5（核心策略逻辑必须有回归保护）
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 测试文件位于 `flutter_logic/test/focus/smart_focus_policy_test.dart`
  - 用 `flutter test` 运行，全部通过，无 error
  - 覆盖三层降级的 **5 条分支**：
    1. 第 1 层命中：`focusedChild != null && canRequestFocus=true` → 直接复用记忆
    2. 第 1 层未命中（focusedChild=null）→ 进第 2 层，命中 `NumericFocusOrder(1.0)`
    3. 第 1 层失效（focusedChild.canRequestFocus=false，模拟 dispose）→ 跳过记忆进第 2 层
    4. 第 2 层全失效（无 OrderedTraversalPolicy 节点或全不可聚焦）→ 进第 3 层 DFS 兜底
    5. 第 3 层也无可用节点 → `targetScope.requestFocus()` 让 scope 自身持有焦点（避免 primaryFocus=null）
  - 断言用 `FocusManager.instance.primaryFocus.debugLabel` 或 `FocusNode.equals` 精确比对落点
- test_tasks:
  - type: unit
    description: 三层降级逻辑 5 条分支覆盖
    scenarios:
      - 记忆命中：focusedChild 有效 → primaryFocus 等于 focusedChild
      - 优先级命中（无记忆）：focusedChild=null → primaryFocus 等于 NumericFocusOrder(1.0) 节点
      - 记忆失效降级：focusedChild.canRequestFocus=false → 跳过记忆，走优先级层
      - 优先级全失效：所有 order 节点 canRequestFocus=false → 走 DFS 兜底
      - 极端兜底：scope 内无任何可聚焦子节点 → primaryFocus 等于 scope 自身或 null-safety 处理
- contract_refs: []
- decision_refs: [D2, D3, D4, D5]
- blocked_files: []

### FF005.1 测试骨架与 FocusScope 测试装置搭建 `⬜`

用 `FlutterWidgetTester` 构造可控的测试装置：包一个 `FocusScope` + 多个 `FocusTraversalOrder` 子节点的测试 helper，便于每条用例快速搭建场景。

```dart
// flutter_logic/test/focus/smart_focus_policy_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/smart_focus_policy.dart';

/// 测试 helper：构造一个挂载 SmartFocusTraversalPolicy 的 FocusScope
/// 内部按 orders 列表创建 N 个 FocusTraversalOrder 子节点
/// 返回 (scopeNode, orderNodes) 便于用例控制 canRequestFocus
Widget _buildTestHarness({
  required List<(double order, String label)> orders,
}) {
  // 用 FocusTraversalGroup(policy: SmartFocusTraversalPolicy()) 包裹
  // 内部 Column 放 orders.map((o) => FocusTraversalOrder(order: NumericFocusOrder(o.order), child: Focus(debugLabel: o.label, child: ...)))
}
```

### FF005.2 三层降级 5 条分支用例编写 `⬜`

按 acceptance_criteria 的 5 条分支逐一编写 `testWidgets` 用例。每条用例：
1. pumpWidget 搭建场景
2. 显式控制 `focusedChild`（通过 `scopeNode.focusedChild` 读 / 通过先 requestFocus 某节点再清除的方式设置）
3. 触发策略（调用 `policy.findFirstFocus(scopeNode)` 或模拟跨 group 方向键事件）
4. 断言 `FocusManager.instance.primaryFocus.debugLabel` 与预期一致

**关键技巧**：
- 模拟"`focusedChild` 已 dispose"：先 `requestFocus(node)`，再 `node.dispose()`（canRequestFocus 自动变 false）
- 模拟"全部不可聚焦"：用 `Focus(canRequestFocus: false, ...)` 构造子节点
- 极端兜底用例：空 `orders` 列表，scope 内无任何子节点

### FF005.3 运行 `flutter test` 验证全部通过 `⬜`

```bash
cd flutter_logic
flutter test test/focus/smart_focus_policy_test.dart
```

**验收**：所有用例 PASS，无 failure，无 error。

---

## R002-FF006：focusable_button_test.dart — FocusableButton widget 测试 `⬜ 待处理`

> 测试目标：FF004 FocusableButton。本任务不新增功能节点，仅验证 FF004 的高亮与生命周期。

- 文件：`flutter_logic/test/focus/focusable_button_test.dart`
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: [R002-FF004]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 测试文件位于 `flutter_logic/test/focus/focusable_button_test.dart`
  - 用 `flutter test` 运行，全部通过，无 error
  - 覆盖 **4 条场景**：
    1. 获得焦点时 `Container.decoration` 有边框 + `Transform.scale` > 1.0
    2. 失去焦点时无边框 + scale = 1.0
    3. `enabled=false` 时 `canRequestFocus=false`（`FocusManager.instance.primaryFocus` 不会落到此节点）
    4. widget unmount 后 `FocusNode.dispose` 被调用（无 use-after-dispose，无内存泄漏）
  - 断言用 `tester.widget<T>(finder)` 或 `tester.firstWidget<T>` 检查实际渲染的 widget 属性
- test_tasks:
  - type: unit
    description: widget 渲染与生命周期验证
    scenarios:
      - 高亮态：requestFocus → 找到 Container/Border/Transform，断言边框颜色 + scale 值
      - 非高亮态：清除焦点 → 断言无边框（decoration=null 或 border=null）
      - 不可聚焦：enabled=false + 模拟方向键 → primaryFocus 不等于此节点
      - 生命周期：pumpWidget 后 pumpWidget 新树（移除此 button）→ 用 addTearDown 验证 _focusNode.dispose 被调用
- contract_refs: []
- decision_refs: [D6]
- blocked_files: []

### FF006.1 widget 测试骨架 `⬜`

```dart
// flutter_logic/test/focus/focusable_button_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/focusable_button.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));
```

### FF006.2 4 条场景用例编写 `⬜`

- **高亮态**：`tester.pumpWidget(_wrap(FocusableButton(label: 'X')))` → 找内部 `Focus` 节点 `requestFocus` → `tester.pumpAndSettle()` → 断言找到 `Container` 且 `decoration` 有 border
- **非高亮态**：承接上例 → 让另一节点获焦 → 断言此 button 的 decoration 无 border
- **不可聚焦**：`FocusableButton(label: 'X', enabled: false)` → 在父 Scope 中模拟方向键 → `expect(FocusManager.instance.primaryFocus?.debugLabel, isNot('X'))`
- **生命周期**：pump 后捕获 `_focusNode` 引用（可暴露测试 only getter 或用 tester 查找）→ pump 新树移除此 widget → 断言 `_focusNode.canRequestFocus == false`（dispose 后此字段变 false）

### FF006.3 运行 `flutter test` 验证全部通过 `⬜`

```bash
cd flutter_logic
flutter test test/focus/focusable_button_test.dart
```

**验收**：所有用例 PASS。

---

## R002-FB005：personal_center_page.dart + main.dart — 页面组装与入口 `⬜ 待处理`

- 文件：
  - `flutter_logic/lib/pages/personal_center_page.dart`（新建）
  - `flutter_logic/lib/main.dart`（修改）
- 改动类型：新建 + 修改
- domain: ui
- task_layer: ui
- depends_on: [R002-FF003, R002-FF004, R002-FB006]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 页面布局：左导航（3 个菜单项）+ 右内容区（至少 3 个按钮含 `NumericFocusOrder` 标签）
  - 左右两个区域各自是独立的 `FocusTraversalGroup`，policy 为 `SmartFocusTraversalPolicy`
  - 右内容区的"会员签到"按钮标 `NumericFocusOrder(1.0)`，"账户信息"标 `NumericFocusOrder(2.0)`，"退出登录"不标 order
  - 底部叠加 `FocusDebugOverlay`，三个调试回调正确接线
  - `main.dart` 的 `home` 改为 `PersonalCenterDemoPage()`
  - `flutter analyze` 无 error
  - `flutter run` 可启动，进入个人中心页面
  - 场景 A 验证通过：按右键焦点落在"会员签到"而非顶部装饰
  - 场景 B 验证通过：切走再回来焦点回到上次位置
  - 场景 C 验证通过：删除当前焦点后按方向键焦点不丢失
- test_tasks:
  - type: integration
    description: 三场景端到端手动验证（场景 A/B/C）
    scenarios:
      - 场景 A 首次进入优先级引导
      - 场景 B 跨区域焦点记忆
      - 场景 C 动态删除节点健壮兜底
- contract_refs: []
- decision_refs: [D1, D7]
- blocked_files: [`flutter_logic/pubspec.yaml`, `app/`, `flutter_logic/.ohos/`]

### FB005.1 页面骨架与左右布局 `⬜`

新建 `flutter_logic/lib/pages/personal_center_page.dart`，搭建左导航 + 右内容区的掌机横屏布局。

```dart
import 'package:flutter/material.dart';
import '../focus/smart_focus_policy.dart';
import '../focus/focusable_button.dart';
import '../debug/focus_debug_overlay.dart';

class PersonalCenterDemoPage extends StatefulWidget {
  const PersonalCenterDemoPage({super.key});

  @override
  State<PersonalCenterDemoPage> createState() => _PersonalCenterDemoPageState();
}

class _PersonalCenterDemoPageState extends State<PersonalCenterDemoPage> {
  // 右内容区按钮列表（场景 3 需要动态删除，故用 setState 管理）
  List<_ButtonItem> _rightButtons = [
    _ButtonItem(label: '会员签到', order: const NumericFocusOrder(1.0)),
    _ButtonItem(label: '账户信息', order: const NumericFocusOrder(2.0)),
    _ButtonItem(label: '退出登录', order: null),
  ];

  String _primaryFocusLabel = 'null';

  @override
  void initState() {
    super.initState();
    FocusManager.instance.addListener(_onFocusChange);
  }

  @override
  void dispose() {
    FocusManager.instance.removeListener(_onFocusChange);
    super.dispose();
  }

  void _onFocusChange() {
    setState(() {
      _primaryFocusLabel = FocusManager.instance.primaryFocus?.debugLabel ?? 'null';
    });
  }

  // build 见 FB005.2
}

class _ButtonItem {
  final String label;
  final FocusOrder? order;
  _ButtonItem({required this.label, this.order});
}
```

### FB005.2 FocusTraversalGroup 嵌套 + FocusTraversalOrder 标记 `⬜`

左右两个 `FocusTraversalGroup` 嵌套，policy 为 `SmartFocusTraversalPolicy`。

```dart
@override
Widget build(BuildContext context) {
  return Scaffold(
    appBar: AppBar(title: const Text('个人中心')),
    body: Stack(
      children: [
        Row(
          children: [
            // 左导航（窄列）
            Expanded(
              flex: 1,
              child: FocusTraversalGroup(
                policy: SmartFocusTraversalPolicy(),
                child: Column(
                  children: [
                    FocusableButton(label: '个人中心'),
                    FocusableButton(label: '设置'),
                    FocusableButton(label: '关于'),
                  ],
                ),
              ),
            ),
            // 右内容区（宽列）
            Expanded(
              flex: 2,
              child: FocusTraversalGroup(
                policy: SmartFocusTraversalPolicy(),
                child: Column(
                  children: _rightButtons
                      .map((item) => FocusableButton(
                            label: item.label,
                            order: item.order,
                          ))
                      .toList(),
                ),
              ),
            ),
          ],
        ),
        // 底部叠加调试浮层（FB005.3）
      ],
    ),
  );
}
```

### FB005.3 叠加 FocusDebugOverlay + 调试回调接线 `⬜`

在 `Stack` 底部叠加 `FocusDebugOverlay`，三个回调分别实现：
- `onDeleteCurrentFocus`：从 `_rightButtons` 移除当前持有焦点的按钮
- `onResetMemory`：调用 `SmartFocusTraversalPolicy.resetMemory` 清空右侧 scope 记忆
- `onPrintRect`：打印右侧 scope 的 `rect` 到 console

```dart
// 在 Stack 的 children 中追加
Positioned(
  bottom: 8,
  left: 8,
  right: 8,
  child: FocusDebugOverlay(
    primaryFocusLabel: _primaryFocusLabel,
    onDeleteCurrentFocus: () {
      // 找到当前 primaryFocus 对应的 _rightButtons 项，setState 移除
      // 注意：用 addPostFrameCallback 确保 setState 完成后再让用户操作
      setState(() {
        final current = FocusManager.instance.primaryFocus?.debugLabel;
        _rightButtons.removeWhere((item) => item.label == current);
      });
    },
    onResetMemory: () {
      // 定位右侧 FocusScopeNode，调用 SmartFocusTraversalPolicy.resetMemory
      // 实现提示：可用 GlobalKey<FocusScopeState> 拿到右侧 scope
    },
    onPrintRect: () {
      // print 右侧 scope 的 rect 用于调试
    },
  ),
),
```

> **时机控制**（B3 审查点）：删除节点的 `setState` 后，`FocusNode` 的 `dispose` 在下一帧生效。`onDeleteCurrentFocus` 回调中用 `WidgetsBinding.instance.addPostFrameCallback` 确保节点确实从树中移除。实际用户操作有自然延迟（点击删除 → 再按方向键），不严格依赖此机制，但调试浮层的删除动作需保证 `setState` 完成。
>
> **测试入口约束**（FB007 依赖）：`PersonalCenterDemoPage` 需将"删除当前焦点"逻辑暴露为 public 方法（建议用 `GlobalKey<_PersonalCenterDemoPageState>` + public `onDeleteCurrentFocus()`），或用 `@visibleForTesting` 标注。FB007 场景 C 集成测试会通过此入口注入删除动作，绕过调试浮层的 button tap。

### FB005.4 main.dart 入口改造 `⬜`

修改 `flutter_logic/lib/main.dart`，将 `home` 从 `MyHomePage` 改为 `PersonalCenterDemoPage`，删除 counter demo 的 `MyHomePage` / `_MyHomePageState`。

```dart
import 'package:flutter/material.dart';
import 'pages/personal_center_page.dart';

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter 焦点 Demo',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const PersonalCenterDemoPage(), // ← 改为 demo 页面
    );
  }
}
```

> 删除原 `MyHomePage` 和 `_MyHomePageState` 类（counter demo 不再需要）。

---

## R002-FB007：focus_demo_test.dart — 三场景集成测试 `⬜ 待处理`

> 测试目标：FB005 PersonalCenterDemoPage。本任务不新增功能节点，自动化验证 analysis 中定义的三场景 A/B/C。依赖 FF005（单元测试）+ FF006（widget 测试）保证底层正确性。

- 文件：
  - `flutter_logic/integration_test/focus_demo_test.dart`（新建）
  - `flutter_logic/pubspec.yaml`（修改，添加 `integration_test` 依赖）
- 改动类型：新建 + 配置
- domain: integration
- task_layer: ui
- depends_on: [R002-FB005, R002-FF005, R002-FF006]
- priority: 5（端到端回归保护）
- risk_tags: [flutter_api_uncertainty]
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `integration_test` 依赖已在 `pubspec.yaml` 的 `dev_dependencies` 中声明（Flutter 官方包）
  - 测试文件位于 `flutter_logic/integration_test/focus_demo_test.dart`
  - 用 `flutter test integration_test/focus_demo_test.dart` 运行（或在 CI 中 `flutter test integration_test/`），全部通过
  - 覆盖 **3 条端到端场景**（对齐 analysis 交互链 + design 时序图）：
    1. **场景 A 优先级**：app 启动 → 按右方向键 → 断言 `primaryFocus.debugLabel == "会员签到"`
    2. **场景 B 记忆**：按下→左→右方向键序列 → 断言 `primaryFocus.debugLabel == "账户信息"`
    3. **场景 C 兜底**：通过 `FB005` 暴露的测试入口触发"删除当前焦点" → 按方向键 → 断言 `primaryFocus != null` 且落到邻近可用节点
  - 场景 C 中节点删除的时序：用 `WidgetsBinding.instance.addPostFrameCallback` 确保 `setState` 完成后再按键
  - 每条场景的断言基于 `FocusManager.instance.primaryFocus.debugLabel`，不依赖肉眼观察
- test_tasks:
  - type: integration
    description: 三场景 A/B/C 端到端自动化
    scenarios:
      - 场景 A：sendKeys arrowRight → expect primaryFocus.debugLabel == '会员签到'
      - 场景 B：sendKeys arrowDown/arrowLeft/arrowRight → expect primaryFocus.debugLabel == '账户信息'
      - 场景 C：触发删除（测试入口）+ addPostFrameCallback + sendKeys arrowDown → expect primaryFocus 非 null 且为预期兜底节点
- contract_refs: []
- decision_refs: [D1, D7]
- blocked_files: []

### FB007.1 integration_test 框架接入 `⬜`

在 `flutter_logic/pubspec.yaml` 的 `dev_dependencies` 添加（不修改其他依赖）：

```yaml
dev_dependencies:
  flutter_test:
    sdk: flutter
  integration_test:
    sdk: flutter
```

在 `flutter_logic/integration_test/focus_demo_test.dart` 初始化 binding：

```dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:flutter_logic/main.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('焦点 demo 三场景', () {
    // FB007.2 在此添加 3 个 testWidgets
  });
}
```

### FB007.2 三场景自动化用例编写 `⬜`

**通用技巧**：
- 模拟方向键：`await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight)`
- 触发删除：FB005 需暴露一个 `@visibleForTesting` 回调或 `GlobalKey` 入口，便于测试代码直接调用 `onDeleteCurrentFocus()`
- 时序保证：删除后 `await tester.pumpAndSettle()` 或 `addPostFrameCallback` + `pump`

**场景 A 用例骨架**：

```dart
testWidgets('场景 A：首次进入优先级引导', (tester) async {
  await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
  await tester.pumpAndSettle();

  // 焦点默认在左侧导航第 1 项
  expect(FocusManager.instance.primaryFocus?.debugLabel, '个人中心');

  // 按右方向键进入右侧内容区
  await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
  await tester.pumpAndSettle();

  // 验证点：焦点落在 NumericFocusOrder(1.0) 的会员签到
  expect(FocusManager.instance.primaryFocus?.debugLabel, '会员签到');
});
```

**场景 B 用例骨架**：

```dart
testWidgets('场景 B：跨区域焦点记忆', (tester) async {
  await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
  await tester.pumpAndSettle();

  // 进右侧会员签到
  await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
  await tester.pumpAndSettle();
  // 下移到账户信息
  await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
  await tester.pumpAndSettle();
  expect(FocusManager.instance.primaryFocus?.debugLabel, '账户信息');

  // 切回左侧
  await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
  await tester.pumpAndSettle();
  // 再回右侧 → 记忆命中
  await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
  await tester.pumpAndSettle();

  expect(FocusManager.instance.primaryFocus?.debugLabel, '账户信息');
});
```

**场景 C 用例骨架**：

```dart
testWidgets('场景 C：动态删除当前焦点健壮兜底', (tester) async {
  await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
  await tester.pumpAndSettle();

  // 焦点放到会员签到
  await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
  await tester.pumpAndSettle();

  // 通过测试入口触发删除（由 FB005 暴露）
  final pageState = tester.state(find.byType(PersonalCenterDemoPage));
  (pageState as dynamic).onDeleteCurrentFocus();  // 或用 GlobalKey
  await tester.pumpAndSettle();  // 等 setState 完成 + 节点 dispose

  // 按方向键触发兜底
  await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
  await tester.pumpAndSettle();

  // 验证点：焦点未丢失，落到下一个可用节点（账户信息）
  expect(FocusManager.instance.primaryFocus, isNotNull);
  expect(FocusManager.instance.primaryFocus?.debugLabel, '账户信息');
});
```

> **测试与 FB005 的耦合点**：场景 C 需要 FB005 暴露删除入口。在 FB005 实现时，将"删除当前焦点"逻辑抽成 public 方法（或用 `@visibleForTesting` 标注），便于集成测试直接调用。此约束需回流到 FB005 任务（已在 FB005 实现提示中说明）。

### FB007.3 运行集成测试验证全部通过 `⬜`

```bash
cd flutter_logic
flutter test integration_test/focus_demo_test.dart
```

**验收**：3 条场景全部 PASS，无 failure，无 error。

> 若场景 C 因时序问题 flaky，检查 `addPostFrameCallback` / `pumpAndSettle` 使用是否正确；若 `findFirstFocus` 未被框架触发（Flutter 版本差异），按 FF003.4 fallback 方案在 `inDirection` 中处理。

---

## 最后：编译验证 + flutter test 全量 + 三场景手动验证 `⬜ 待处理`

依赖 R002-FB007 完成后执行。

### 验证步骤

```bash
cd flutter_logic
flutter analyze                        # 无 error
flutter test                           # 单元 + widget 测试全部通过
flutter test integration_test/         # 集成测试 3 场景全部通过
flutter run                            # 启动 demo 做手动验证（见下方）
```

### 场景 A：首次进入优先级引导（验证 FF003 第 2 层）

1. 进入页面，焦点默认在左侧导航"个人中心"
2. 按右方向键进入右侧内容区
3. **验证点**：焦点精准落在"会员签到"（NumericFocusOrder(1.0)）上，不是顶部装饰或物理第一个

### 场景 B：跨区域焦点记忆（验证 FF003 第 1 层）

1. 焦点在右侧"会员签到"
2. 按下方向键移到"账户信息"
3. 按左方向键回左侧导航
4. 再按右方向键回右侧内容区
5. **验证点**：焦点回到"账户信息"，不是"会员签到"

### 场景 C：动态删除节点健壮兜底（验证 FF003 第 3 层）

1. 焦点在某按钮
2. 点调试浮层"删除当前焦点"
3. 按方向键
4. **验证点**：焦点落到邻近可用节点，不丢失

### 附加验证：重置记忆

1. 走完场景 B 后（焦点在"账户信息"记忆中）
2. 点调试浮层"重置记忆"
3. 按左方向键回左侧，再按右方向键回右侧
4. **验证点**：焦点重新走优先级层，回到"会员签到"（记忆被清空）
