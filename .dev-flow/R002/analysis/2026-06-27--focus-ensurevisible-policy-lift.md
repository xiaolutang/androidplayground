---
date: 2026-06-27
topic: focus-ensurevisible-policy-lift
type: analysis
requirement_cycle: R002
related_fix: R002-FIX005
status: analyzed
---

# 焦点 ensureVisible 链路下沉到 policy 层 — 根因分析

## 问题表象

跨 scope 方向键导航到右内容区"退出登录"按钮时：
1. `scrollOffset` 保持 0（不自动滚动）
2. 按钮底部被 `SingleChildScrollView` 的 `Clip.hardEdge` 裁剪
3. 按钮落进 iPhone home indicator 安全区被遮挡

## 错误的中间结论（已纠正）

最初判断"Flutter SDK 不自动 ensureVisible，需要在 widget 层手动补"。
这个判断基于记忆，没有读源码，是错的。

## SDK 源码证据

### 1. `requestFocusCallback` 是 SDK 的官方 hook

`packages/flutter/lib/src/widgets/focus_traversal.dart:184`
```dart
final TraversalRequestFocusCallback requestFocusCallback;
```

`focus_traversal.dart:189-204`（默认实现）
```dart
TraversalRequestFocusCallback defaultTraversalRequestFocusCallback = (
    FocusNode node, {
    ScrollPositionAlignmentPolicy? alignmentPolicy,
    double? alignment,
    Duration? duration,
    Curve? curve,
}) {
  node.requestFocus();
  Scrollable.ensureVisible(
    node.context!,   // ← 关键：自动滚动
    alignmentPolicy: alignmentPolicy ?? ScrollPositionAlignmentPolicy.explicit,
    alignment: alignment ?? 0,
    duration: duration ?? Scrollable.kDuration,
    curve: curve ?? Scrollable.kCurve,
  );
};
```

`FocusNode.context` 是公开 nullable getter（`focus_manager.dart:618`）。

### 2. SDK 自带的 `DirectionalFocusTraversalPolicyMixin` 用同一 hook

`focus_traversal.dart:1055-1069`
```dart
if (found != null) {
  _pushPolicyData(direction, nearestScope, focusedChild);
  switch (direction) {
    case TraversalDirection.up:
    case TraversalDirection.left:
      requestFocusCallback(
        found,
        alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtStart,
      );
    case TraversalDirection.down:
    case TraversalDirection.right:
      requestFocusCallback(
        found,
        alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
      );
  }
  return true;
}
```

**结论**：系统的焦点查找策略**也是**通过 `requestFocusCallback` 触发滚动的。

## 我们的 policy 为什么失效

`SmartFocusTraversalPolicy` 在 `_smartRequestFocus`（三层降级）和
`inDirection`（同 scope 候选路径）中共 4 处直接调用：

```dart
node.requestFocus();   // ← 裸 requestFocus，绕过 hook
```

`FocusNode.requestFocus()` 只移动焦点，不触发 `ensureVisible`。
自定义 policy override 了 `inDirection`，SDK 的默认 `requestFocusCallback`
链路就不再被走到，跨 scope 导航的滚动功能丢失。

之前的"修复"是在 `FocusableButton` 里加 `_handleFocusChange`：
```dart
_focusNode.addListener(() {
  if (_focusNode.hasFocus) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Scrollable.ensureVisible(_focusNode.context!, alignment: 0.5);
    });
  });
});
```

这是 widget 层补丁，根因在 policy 层。

## 系统性修复

将 4 处 `.requestFocus()` 改为 `requestFocusCallback(node, alignment: 0.5)`：

```dart
// _smartRequestFocus 三层降级 × 3
requestFocusCallback(remembered, alignment: 0.5);
requestFocusCallback(priorityFirst, alignment: 0.5);
requestFocusCallback(fallback, alignment: 0.5);

// inDirection 同 scope 候选 × 1
requestFocusCallback(candidate, alignment: 0.5);
```

第 4 层极端兜底（`targetScope.requestFocus()`）保留不改：
scope 节点 context 可能为 null（attach 在 FocusManager 而非 widget），
走 requestFocusCallback 内部的 `node.context!` 会崩。

删除 `FocusableButton._handleFocusChange` 及 initState/dispose 注册。

## 为什么 alignment: 0.5 而不是 SDK 默认的 keepVisibleAtEnd

对照实验证据：

| alignment 策略 | 退出登录 bottom | viewport bottom | home indicator 上沿 | 结果 |
|---|---|---|---|---|
| `keepVisibleAtEnd`（SDK 默认） | 366.0 | 356.0 | 356.0 | ❌ 被遮挡 10px |
| `alignment: 0.5`（强制居中） | 完全可见 | - | - | ✅ |

`keepVisibleAtEnd` 只对齐到视口 bottom（含安全区），底部按钮会落进
home indicator 被遮挡。`alignment: 0.5` 把节点对齐到视口中心，
强制额外滚动一段，绕开 safe area。

## 验证

- `test/focus/focus_ensure_visible_test.dart`：三个关键断言全绿
  - `scrollState.position.pixels > 0`（ensureVisible 触发）
  - `lastRect.bottom <= vpRect.bottom + 1`（不被 Clip 裁）
  - `lastRect.bottom <= logicalSize.height - homeIndicator + 1`（不被安全区遮挡）
- 全量 widget 测试 + 集成测试通过
- 对照实验：删除 widget 层 `_handleFocusChange` 后，所有测试仍通过
  （证明滚动能力已由 policy 层接管，不依赖 widget 层补丁）

## 教训

1. **不要基于记忆下结论**：SDK 行为必须读源码确认
2. **widget 层补丁要警惕**：能"work"不代表根因解决，往往掩盖了上层 API 误用
3. **优先用 SDK 官方 hook**：`requestFocusCallback` 是 policy 的扩展点，
   自定义 policy 必须走这个 hook 才能保留 SDK 的所有链路（这里就是 ensureVisible）
