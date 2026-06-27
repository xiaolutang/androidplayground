---
version: "1.0"
type: tasks
topic: focus-boundary-shake-feedback
requirement_cycle: R004
workflow:
  evaluate_provider: local
  mode: auto
status: archived
---

# 焦点边界受阻抖动反馈 — 前端任务清单

基于 `analysis/2026-06-27--focus-boundary-shake-feedback-frontend.md` 设计，
将设计方案拆解为可逐条执行的任务。

[全局约束]
- 技术栈：Flutter（flutter_logic/ 模块），不引入 MethodChannel/EventChannel
- 不修改 architecture.md（INV-1 不变量保持）
- 禁止修改：`lib/main.dart`、`lib/home_page.dart`、`lib/debug/focus_debug_overlay.dart`、SDK 源码
- 抖动参数硬编码：±4px / 250ms / 3 周期 sin 波（OI-1 留作 visual-verify 后微调）
- 全部使用 Flutter SDK 内置 API，不新增第三方依赖
- 参考已有代码：`lib/focus/smart_focus_policy.dart`（FF003）、`lib/focus/focusable_button.dart`（FF004）

---

## 执行顺序

1. ⬜ 任务 1 — R004-FF005 信号通道：SmartFocusTraversalPolicy 新增 blockedDirectionNotifier（无依赖）
   - ⬜ FF005.1 新增 ValueNotifier 字段 + 构造初始化
   - ⬜ FF005.2 垂直 return false 路径前写入 notifier
   - ⬜ FF005.3 水平 super.inDirection 返回 false 后写入 notifier
   - ⬜ FF005.4 PersonalCenterDemoPage dispose 释放 notifier
2. ⬜ 任务 2 — R004-FB008 抖动反馈：FocusableButton 订阅 notifier + 方向感知抖动（依赖 FF005）
   - ⬜ FB008.1 新增 blockedNotifier 入参
   - ⬜ FB008.2 State 内新增 AnimationController + CurvedAnimation
   - ⬜ FB008.3 _onBlocked listener：reset notifier + hasFocus 判断 + forward(from:0)
   - ⬜ FB008.4 build 用 AnimatedBuilder + Transform.translate 包裹 child
   - ⬜ FB008.5 失焦/其他方向键 stop 抖动
   - ⬜ FB008.6 dispose 释放 controller + removeListener
   - ⬜ FB008.7 PersonalCenterDemoPage 装配：所有 FocusableButton 注入 notifier
3. ⬜ 任务 3 — R004-FF005 单元测试：boundary_notifier_test.dart（依赖 FF005）
4. ⬜ 任务 4 — R004-FB008 单元测试：focusable_button_shake_test.dart（依赖 FB008）
5. ⬜ 任务 5 — R004-FF009 集成测试：boundary_shake_integration_test.dart（依赖 FF005 + FB008）
6. ⬜ 最后 — 编译验证 + 全量测试路径

---

## R004-FF005：smart_focus_policy.dart + personal_center_page.dart — 信号通道 `⬜ 待处理`

- 文件：
  - `flutter_logic/lib/focus/smart_focus_policy.dart`（修改）
  - `flutter_logic/lib/pages/personal_center_page.dart`（修改 dispose）
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 实现 1 个稳定标识（personal_center.policy.blocked_notifier，清单见 AcceptanceSpec）
  - SmartFocusTraversalPolicy 暴露 `blockedDirectionNotifier`（类型 `ValueNotifier<TraversalDirection?>`，初始 value=null）
  - 垂直方向（up/down）无候选时，在 `return false` **之前**写入 `notifier.value = direction`
  - 水平方向 `super.inDirection` 返回 false 时，写入 `notifier.value = direction`
  - 正常焦点切换（有候选）时，notifier.value 保持 null，不误触发
  - PersonalCenterDemoPage 在 dispose 时调用 `_parentPolicy.blockedDirectionNotifier.dispose()`
  - `flutter analyze` 无 error
  - `flutter test test/focus/`（现有 R002 测试）全部通过（向后兼容）
  - visual-verify PASS（FF005 本身无视觉变化，由 FB008 端到端集成测试 FF009 承接验证）
- test_tasks:
  - type: unit
    description: FF005 信号通道单元测试（详见任务 3）
    scenarios: [写入时机-vertical, 写入时机-horizontal, 正常路径不写入, reset 行为]
- contract_refs: []
- decision_refs: []
- blocked_files:
  - `flutter_logic/lib/main.dart`
  - `flutter_logic/lib/home_page.dart`
  - `flutter_logic/lib/debug/focus_debug_overlay.dart`

### FF005.1 新增 blockedDirectionNotifier 字段 `⬜`

在 `SmartFocusTraversalPolicy` 类顶部（`_orderedPolicy` 字段后）新增：

```dart
/// 焦点边界受阻信号通道（R004-FF005）。
///
/// 在 [inDirection] 判定无候选（垂直列聚类无结果 / 水平 super 无结果）
/// 即将 return false 之前写入受阻方向；widget 订阅后据此触发抖动反馈。
///
/// 消费方（FocusableButton._onBlocked）读取后立即置 null，保证单次按键
/// 只触发一次抖动。
final ValueNotifier<TraversalDirection?> blockedDirectionNotifier =
    ValueNotifier<TraversalDirection?>(null);
```

理由：final 字段 + 构造时初始化，与现有 `_orderedPolicy` 一致；policy 本身无 dispose 生命周期，notifier 由持有 policy 的页面在 dispose 时释放。

### FF005.2 垂直 return false 路径前写入 notifier `⬜`

修改 `smart_focus_policy.dart:177-180` 区块：

```dart
// 修改前
if (direction == TraversalDirection.up ||
    direction == TraversalDirection.down) {
  return false;
}

// 修改后
if (direction == TraversalDirection.up ||
    direction == TraversalDirection.down) {
  blockedDirectionNotifier.value = direction;  // 受阻信号
  return false;
}
```

理由：在 return false **之前**写入，保证 listener 在 inDirection 调用栈内被触发，此时焦点状态未变，widget 的 hasFocus 判断可靠。

### FF005.3 水平 super.inDirection 返回 false 后写入 notifier `⬜`

修改 `smart_focus_policy.dart:181` 区块：

```dart
// 修改前
return super.inDirection(currentNode, direction);

// 修改后
final result = super.inDirection(currentNode, direction);
if (!result) {
  blockedDirectionNotifier.value = direction;  // 受阻信号
}
return result;
```

理由：先暂存 super 的返回值，false 时写入信号，再返回。保持 return 语义不变。

### FF005.4 PersonalCenterDemoPage dispose 释放 notifier `⬜`

修改 `personal_center_page.dart:63-68` 的 dispose：

```dart
@override
void dispose() {
  FocusManager.instance.removeListener(_onFocusChange);
  _parentPolicy.blockedDirectionNotifier.dispose();  // 新增
  _primaryFocusLabel.dispose();
  super.dispose();
}
```

理由：页面是 policy 实例的唯一持有者，页面销毁时 notifier 也应释放，避免 ValueNotifier 泄漏。

---

## R004-FB008：focusable_button.dart + personal_center_page.dart — 抖动反馈 `⬜ 待处理`

- 文件：
  - `flutter_logic/lib/focus/focusable_button.dart`（修改）
  - `flutter_logic/lib/pages/personal_center_page.dart`（修改装配点）
- 改动类型：修改
- domain: ui
- task_layer: business
- depends_on: [R004-FF005]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - FocusableButton 新增可选入参 `blockedNotifier`（类型 `ValueNotifier<TraversalDirection?>?`，默认 null）
  - 不传 blockedNotifier 时，行为与 R002 完全一致（向后兼容，现有 43 个测试不受影响）
  - 传入 blockedNotifier 且自身 primaryFocus 时：
    - 收到 up/down → Transform.translate.dy 在 ±4px 振荡，dx=0
    - 收到 left/right → Transform.translate.dx 在 ±4px 振荡，dy=0
    - 抖动持续约 250ms（3 周期 sin 波），结束后 Transform.translate 归零
  - 动画进行中再次收到同方向信号 → forward(from:0) 重启，不堆叠
  - 抖动中失焦（FocusNode.hasFocus 变 false）→ 立即 stop + Transform 归零
  - 非 primaryFocus 收到信号 → 不抖动
  - widget dispose 时：_shakeController.dispose() + blockedNotifier.removeListener(_onBlocked)
  - PersonalCenterDemoPage 所有 FocusableButton（左导航 3 个 + 右内容区 5 个）均注入 parentPolicy.blockedDirectionNotifier
  - 实现 4 个稳定标识（personal_center.left_nav.button / personal_center.right_content.button / personal_center.button.shake_transform / personal_center.policy.blocked_notifier，清单见 AcceptanceSpec）
  - visual-verify PASS（三层证据对照 AcceptanceSpec）
  - `flutter analyze` 无 error
- test_tasks:
  - type: unit
    description: FB008 抖动反馈单元测试（详见任务 4）
    scenarios: [方向感知垂直, 方向感知水平, 非焦点不抖, 防抖重启, dispose 无 leak]
  - type: integration
    description: 端到端受阻抖动集成测试（详见任务 5）
    scenarios: [垂直边界受阻抖动, 水平边界受阻抖动, 连续按键防抖, 失焦取消]
- contract_refs: []
- decision_refs: []
- blocked_files:
  - `flutter_logic/lib/main.dart`
  - `flutter_logic/lib/home_page.dart`
  - `flutter_logic/lib/debug/focus_debug_overlay.dart`

### FB008.1 新增 blockedNotifier 入参 `⬜`

在 `FocusableButton` StatefulWidget 字段区（`autofocus` 后）新增：

```dart
/// 焦点边界受阻信号通道（R004-FB008）。
///
/// 非 null 时，State 内订阅此 notifier；当 policy 写入方向且自身是
/// primaryFocus 时启动方向感知抖动。
/// null 时行为与 R002 完全一致（向后兼容）。
final ValueNotifier<TraversalDirection?>? blockedNotifier;
```

构造函数同步加参数（在 `this.autofocus = false` 后）：

```dart
this.blockedNotifier,
```

### FB008.2 State 内新增 AnimationController + CurvedAnimation `⬜`

`_FocusableButtonState` 改为混入 `SingleTickerProviderStateMixin`：

```dart
class _FocusableButtonState extends State<FocusableButton>
    with SingleTickerProviderStateMixin {
```

initState 新增：

```dart
late final AnimationController _shakeController = AnimationController(
  duration: const Duration(milliseconds: 250),
  vsync: this,
);
// _shakeAnimation.value ∈ [-1, 1]（sin 波归一化）
// 实际位移在 builder 内乘以 amplitude（4.0）得到 ±4px。
// 关键：value=0（controller 未启动/已结束）时 sin=0 → 位移=0，无 idle 偏移。
late final Animation<double> _shakeAnimation = _shakeController
    .drive(CurveTween(_ShakeCurve())); // 3 周期 sin 波，见下方
```

在文件底部新增 `_ShakeCurve`（实现 3 周期 sin 波形）：

```dart
/// 3 周期 sin 波形 Curve：t∈[0,1] → sin(3*2π*t) ∈ [-1, 1]。
/// 配合 Tween(begin:-2, end:2) 把 [-1,1] 映射到位移 px。
class _ShakeCurve extends Curve {
  @override
  double transformInternal(double t) {
    return math.sin(3 * 2 * math.pi * t); // 3 周期
  }
}
```

需新增 import：`import 'dart:math' as math;`

### FB008.3 _onBlocked listener：reset + hasFocus 判断 + forward(from:0) `⬜`

新增 listener 方法 + 在 initState 注册：

```dart
late final VoidCallback _onBlocked;

@override
void initState() {
  super.initState();
  _focusNode = FocusNode(debugLabel: widget.label);
  _focusNode.canRequestFocus = widget.enabled;
  _onBlocked = _handleBlocked;
  widget.blockedNotifier?.addListener(_onBlocked);
}

void _handleBlocked() {
  final notifier = widget.blockedNotifier;
  if (notifier == null) return;
  final dir = notifier.value;
  if (dir == null) return;
  if (!_focusNode.hasFocus) return;  // 非焦点不抖
  notifier.value = null;  // 先 reset，避免重入
  _shakeController.forward(from: 0);  // 防抖：重启而非堆叠
}
```

理由：先 reset 再 forward，保证单次按键只触发一次；forward(from:0) 对进行中的 controller 会重置 progress，幂等无堆叠。

didUpdateWidget 同步 notifier 引用（若父 widget 重建传入新 notifier）：

```dart
@override
void didUpdateWidget(covariant FocusableButton oldWidget) {
  super.didUpdateWidget(oldWidget);
  // ... 现有 label/enabled 逻辑 ...
  if (oldWidget.blockedNotifier != widget.blockedNotifier) {
    oldWidget.blockedNotifier?.removeListener(_onBlocked);
    widget.blockedNotifier?.addListener(_onBlocked);
  }
}
```

### FB008.4 build 用 AnimatedBuilder + Transform.translate 包裹 child `⬜`

在现有 `AnimatedContainer` 外层（或 InkWell 内层，取决于 clip 评估）用 AnimatedBuilder 包裹：

```dart
child: AnimatedBuilder(
  animation: _shakeAnimation,
  builder: (context, child) {
    // 方向感知：通过 notifier 最近一次的方向判断轴
    // 由于 forward 时方向已 reset，需在 _handleBlocked 内暂存 _shakeAxis
    // amplitude=4.0（±4px），value∈[-1,1] → 位移∈[-4,4]，idle 时 value=0 → 位移=0
    const double amplitude = 4.0;
    final dx = _shakeAxis == _ShakeAxis.horizontal ? _shakeAnimation.value * amplitude : 0.0;
    final dy = _shakeAxis == _ShakeAxis.vertical ? _shakeAnimation.value * amplitude : 0.0;
    return Transform.translate(
      offset: Offset(dx, dy),
      child: child,
    );
  },
  child: <现有的 AnimatedContainer + InkWell + Text>,
),
```

新增辅助状态：

```dart
enum _ShakeAxis { horizontal, vertical, none }
_ShakeAxis _shakeAxis = _ShakeAxis.none;
```

在 `_handleBlocked` 内根据方向设置：

```dart
_shakeAxis = (dir == TraversalDirection.up || dir == TraversalDirection.down)
    ? _ShakeAxis.vertical
    : _ShakeAxis.horizontal;
```

理由：±4px 等于 `margin: horizontal:4` 的内缩空间，Transform.translate 不会导致 border 超出 SingleChildScrollView clip 边界（与 R002-FIX002 教训一致）。OI-1 visual-verify 后由 ±2px/margin:2 调整为 ±4px/margin:4。

### FB008.5 失焦/其他方向键 stop 抖动 `⬜`

在 initState 给 _focusNode 加 listener：

```dart
_focusNode.addListener(_onFocusChanged);
```

新增：

```dart
void _onFocusChanged() {
  if (!_focusNode.hasFocus && _shakeController.isAnimating) {
    _shakeController.stop();
    _shakeAxis = _ShakeAxis.none;
  }
}
```

理由：抖动中按其他方向键导致焦点切换 → 失焦 → 立即停止抖动，Transform 归零，让位给正常焦点逻辑。

### FB008.6 dispose 释放 controller + removeListener `⬜`

修改 dispose：

```dart
@override
void dispose() {
  _disposed = true;
  widget.blockedNotifier?.removeListener(_onBlocked);
  _focusNode.removeListener(_onFocusChanged);
  _shakeController.dispose();
  _focusNode.dispose();
  super.dispose();
}
```

### FB008.7 PersonalCenterDemoPage 装配：所有 FocusableButton 注入 notifier `⬜`

修改 `personal_center_page.dart`：

左导航（line 178-183 区块）每个 FocusableButton 加 `blockedNotifier: _parentPolicy.blockedDirectionNotifier`：

```dart
FocusableButton(
  label: '个人中心',
  autofocus: true,
  blockedNotifier: _parentPolicy.blockedDirectionNotifier,
),
// 设置、关于 同理
```

右内容区（line 215-218 区块）FocusableButton 同理：

```dart
FocusableButton(
  label: item.label,
  order: item.order,
  blockedNotifier: _parentPolicy.blockedDirectionNotifier,
),
```

理由：所有按钮订阅同一个页面级 notifier；policy 写入时，只有当前 primaryFocus 的按钮会抖动（_handleBlocked 内 hasFocus 判断）。

---

## R004-FF005-TEST：boundary_notifier_test.dart — FF005 单元测试 `⬜ 待处理`

- 文件：`flutter_logic/test/focus/boundary_notifier_test.dart`（新建）
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: [R004-FF005]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 测试覆盖 4 个场景：垂直写入时机、水平写入时机、正常路径不写入、reset 行为
  - 所有测试真实执行（非 skip），全部 PASS
  - `flutter test test/focus/boundary_notifier_test.dart` 通过
- test_tasks:
  - type: unit
    description: FF005 信号通道单元测试
    scenarios:
      - "[垂直写入时机] 构造 policy + FocusScope，焦点在顶部按钮按上键，断言 notifier.value == TraversalDirection.up（在 return false 前）"
      - "[水平写入时机] 焦点在最左按钮按左键，断言 notifier.value == TraversalDirection.left"
      - "[正常路径不写入] 焦点在中间按钮按下键（有候选），断言 notifier.value == null"
      - "[reset 行为] 模拟 widget 消费方把 notifier.value 置 null，再次按键能重新写入"
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF005-TEST.1 测试骨架 `⬜`

测试结构：

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/smart_focus_policy.dart';
// 需测试工具：构造最小 FocusScope + FocusTraversalGroup + 多个 Focus 节点

void main() {
  group('FF005 blockedDirectionNotifier', () {
    testWidgets('[垂直写入时机] 焦点在顶部按钮按上键 → notifier.value == up',
        (tester) async {
      // 1. 构造 SmartFocusTraversalPolicy
      // 2. 包裹 FocusTraversalGroup(policy) + Column[Focus(label=A, autofocus), Focus(label=B)]
      // 3. pumpAndSettle
      // 4. sendKeyEvent(arrowUp)
      // 5. 断言 policy.blockedDirectionNotifier.value == TraversalDirection.up
    });

    testWidgets('[水平写入时机] 焦点在最左按钮按左键 → notifier.value == left',
        (tester) async {
      // 类似，布局为 Row[Focus(A), Focus(B)]
    });

    testWidgets('[正常路径不写入] 有候选时 notifier.value 保持 null',
        (tester) async {
      // 布局 Column[Focus(A, autofocus), Focus(B)]
      // 按下键（A→B 有候选）
      // 断言 notifier.value == null
    });

    testWidgets('[reset 行为] 消费后置 null，再次按键能重新写入',
        (tester) async {
      // 第一次按键写入 up，手动置 null
      // 再次按上键，断言 value 再次 == up
    });
  });
}
```

理由：FF005 是纯逻辑层（policy 字段），不需要 widget 渲染抖动，测试最小化；用 FocusTraversalGroup 包裹即可触发 inDirection。

---

## R004-FB008-TEST：focusable_button_shake_test.dart — FB008 单元测试 `⬜ 待处理`

- 文件：`flutter_logic/test/focus/focusable_button_shake_test.dart`（新建）
- 改动类型：新建
- domain: ui
- task_layer: business
- depends_on: [R004-FB008]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 测试覆盖 5 个场景：方向感知垂直、方向感知水平、非焦点不抖、防抖重启、dispose 无 leak
  - 所有测试真实执行（非 skip），全部 PASS
  - `flutter test test/focus/focusable_button_shake_test.dart` 通过
- test_tasks:
  - type: unit
    description: FB008 抖动反馈单元测试
    scenarios:
      - "[方向感知垂直] primaryFocus + 收到 up → Transform.translate.dy 振荡/dx=0"
      - "[方向感知水平] primaryFocus + 收到 left → Transform.translate.dx 振荡/dy=0"
      - "[非焦点不抖] 非 primaryFocus 收到信号 → Transform.translate 保持 0"
      - "[防抖重启] 动画中再次收到信号 → forward(from:0)，无第二个 controller"
      - "[dispose 无 leak] widget unmount → controller.dispose + removeListener 被调用"
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB008-TEST.1 测试骨架 `⬜`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/focusable_button.dart';

void main() {
  group('FB008 FocusableButton shake', () {
    testWidgets('[方向感知垂直] primaryFocus + up → dy 振荡, dx=0', (tester) async {
      // 1. 构造 ValueNotifier<TraversalDirection?>(null)
      // 2. FocusableButton(label:'A', autofocus:true, blockedNotifier:notifier)
      // 3. pumpAndSettle
      // 4. notifier.value = TraversalDirection.up
      // 5. pump(Duration(milliseconds: 50))  // 抖动中
      // 6. 找 Transform，断言 translate.dy.abs() > 0 && translate.dx == 0
      // 7. pump(Duration(milliseconds: 300))  // 结束
      // 8. 断言 Transform.translate = Offset.zero
    });

    testWidgets('[方向感知水平] primaryFocus + left → dx 振荡, dy=0', (tester) async {
      // 类似，notifier.value = left，断言 dx≠0, dy=0
    });

    testWidgets('[非焦点不抖] 非 primaryFocus → Transform 保持 0', (tester) async {
      // Column[FocusableButton(A, autofocus), FocusableButton(B, blockedNotifier)]
      // notifier.value = up
      // 断言 B 的 Transform.translate == Offset.zero
    });

    testWidgets('[防抖重启] 动画中再次信号 → forward(from:0)', (tester) async {
      // notifier.value = up; pump(100ms)
      // 记录 progress1 = controller.value
      // notifier.value = up 再次（需先 reset null 再写 up）
      // pump(50ms)
      // 断言 controller.value < progress1（因 from:0 重启）或通过间接行为验证重启
    });

    testWidgets('[dispose 无 leak] unmount → controller.dispose + removeListener',
        (tester) async {
      // 挂载 FocusableButton，拿到 State
      // unmount（pumpWidget Container()）
      // 断言 state.isDisposed == true
      // 断言 notifier 不再有 listener（notifier.value=X 不触发回调）
    });
  });
}
```

---

## R004-FF009：boundary_shake_integration_test.dart — 端到端集成测试 `⬜ 待处理`

- 文件：`flutter_logic/test/focus/boundary_shake_integration_test.dart`（新建）
- 改动类型：新建
- domain: integration
- task_layer: business
- depends_on: [R004-FF005, R004-FB008]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 测试覆盖 4 个端到端场景：垂直边界受阻抖动、水平边界受阻抖动、连续按键防抖、失焦取消
  - 所有测试真实执行（非 skip），全部 PASS
  - `flutter test test/focus/boundary_shake_integration_test.dart` 通过
  - 测试中真实加载 PersonalCenterDemoPage（非 mock），真实按键事件
- test_tasks:
  - type: integration
    description: 端到端受阻抖动集成测试
    scenarios:
      - "[垂直边界] 焦点到会员签到按上键 → Transform.translate.dy 振荡 + 焦点不变"
      - "[水平边界] 焦点到个人中心按左键 → Transform.translate.dx 振荡 + 焦点不变"
      - "[连续防抖] 连按 3 次上键（间隔 80ms）→ 无堆叠，最后一次后 250ms 结束"
      - "[失焦取消] 抖动中按下键切换焦点 → 原按钮抖动立即停止"
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FF009.1 集成测试骨架 `⬜`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';

void main() {
  group('R004 端到端受阻抖动', () {
    testWidgets('[垂直边界] 会员签到按上键 → dy 振荡 + 焦点不变', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
      await tester.pumpAndSettle();

      // 焦点到会员签到（右内容区顶部）
      // 初始 autofocus 在左导航"个人中心"，需通过方向键导航到右侧
      // 或直接通过 FocusNode 拿到"会员签到"节点 requestFocus
      final signInNode = find.ancestor(
        of: find.text('会员签到'),
        matching: find.byType(Focus),
      );
      await tester.ensureVisible(find.text('会员签到'));

      // 按上键（边界）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump(Duration(milliseconds: 50));  // 抖动中

      // 找到会员签到按钮的 Transform
      final transform = find.descendant(
        of: find.widgetWithText(FocusableButton, '会员签到'),
        matching: find.byType(Transform),
      ).evaluate().first;

      final renderObject = (transform as Element).renderObject as RenderTransform;
      expect(renderObject.transform.getTranslation().dy, isNonZero);
      expect(renderObject.transform.getTranslation().dx, equals(0.0));

      // 等待抖动结束
      await tester.pumpAndSettle();
      expect(renderObject.transform.getTranslation(), equals(Offset.zero));

      // 焦点仍在会员签到
      expect(FocusManager.instance.primaryFocus?.debugLabel, '会员签到');
    });

    testWidgets('[水平边界] 个人中心按左键 → dx 振荡', (tester) async {
      // 个人中心是 autofocus，直接按左键
      // 断言 Transform.translate.dx 振荡，dy=0
    });

    testWidgets('[连续防抖] 连按 3 次上键（80ms 间隔）→ 无堆叠', (tester) async {
      // 焦点到会员签到
      // for 3 times: sendKeyEvent(arrowUp); pump(80ms)
      // 断言无多个 AnimationController（间接：抖动平滑无跳跃）
      // 最后 pumpAndSettle，Transform 归零
    });

    testWidgets('[失焦取消] 抖动中按下键切换焦点 → 原按钮停止', (tester) async {
      // 焦点到会员签到，按上键启动抖动
      // pump(50ms)
      // 按下键（焦点切换到账户信息）
      // pump(10ms)
      // 断言会员签到的 Transform.translate == Offset.zero（已 stop）
    });
  });
}
```

理由：集成测试必须真实加载 PersonalCenterDemoPage（非 mock policy），通过真实 sendKeyEvent 触发完整链路（SDK → policy.inDirection → notifier 写入 → FocusableButton 订阅 → 抖动）。这是验证"真实完成"的关键。

---

## 最后：编译验证 + 全量测试 `⬜ 待处理`

完成所有任务后执行：

```bash
cd flutter_logic
flutter analyze                              # 无 error
flutter test                                 # 全量（R002 既有 + R004 新增）全 PASS
flutter test test/focus/boundary_notifier_test.dart
flutter test test/focus/focusable_button_shake_test.dart
flutter test test/focus/boundary_shake_integration_test.dart
```

验收：
- `flutter analyze` 无 error
- 全量 `flutter test` PASS（含 R002 既有 43 个 + R004 新增 ≥13 个）
- 任何 R002 既有测试不得回归失败（向后兼容验证）
