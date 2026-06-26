import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

/// 自定义焦点遍历策略：记忆 > 优先级 > 物理兜底三层降级。
///
/// 挂在 [FocusTraversalGroup.policy] 上，方向键触发时被 Flutter 焦点系统回调。
///
/// ## 触发机制（R002-FF003 修复后）
///
/// Flutter SDK 方向键的实际调用链：
/// 1. `FocusNode.focusInDirection()` →
///    `FocusTraversalGroup.of(context).inDirection(this, direction)`
/// 2. `DirectionalFocusTraversalPolicyMixin.inDirection()` 默认实现：
///    - `focusedChild == null` → 调用 `findFirstFocusInDirection()`（几何排序）
///    - `focusedChild != null` → 走 `_sortAndFilterHorizontally/Vertically`
///      （几何就近）
/// 3. **两条路径都不调用 `findFirstFocus()`**
///
/// 因此，本类重写 [inDirection] 来拦截方向键事件：
/// - 先在方向轴上做几何排序找候选目标节点。
/// - 检查候选是否与当前焦点跨越了 [FocusTraversalGroup] 边界。
/// - 若**跨 group**：对目标 group 的 scope 执行三层降级（记忆>优先级>兜底）。
/// - 若**同 group 内**：直接聚焦候选，保持几何就近。
///
/// ## 三层降级顺序
/// 1. **记忆层**：复用 [FocusScopeNode.focusedChild]（SDK 自动维护的上次焦点子节点）。
/// 2. **优先级层**：委托 [OrderedTraversalPolicy.findFirstFocus] 找
///    [NumericFocusOrder] 最小节点。
/// 3. **物理兜底层**：DFS 递归 [_findFirstFocusableChild] 找第一个
///    [FocusNode.canRequestFocus]=true 的节点。
/// 4. **极端兜底**：让 [FocusScopeNode] 自身持有焦点，避免 primaryFocus=null。
///
/// scope 内部的 tab 顺序由 [sortDescendants] 委托 [_orderedPolicy] 走
/// [NumericFocusOrder]。
class SmartFocusTraversalPolicy extends FocusTraversalPolicy
    with DirectionalFocusTraversalPolicyMixin {
  /// 内部复用一个 [OrderedTraversalPolicy] 实例做优先级层委托与排序。
  final OrderedTraversalPolicy _orderedPolicy = OrderedTraversalPolicy();

  /// 三层降级：记忆 → 优先级 → 物理兜底。命中即返回 true。
  ///
  /// 这是整个 demo 的命脉，每层的命中/未命中判断必须严谨。
  @visibleForTesting
  bool smartRequestFocus(FocusScopeNode targetScope) => _smartRequestFocus(targetScope);

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

  /// DFS 递归找第一个 [FocusNode.canRequestFocus]=true 的后代节点。
  ///
  /// 跳过 canRequestFocus=false 的节点（含已 dispose 的节点）。
  @visibleForTesting
  FocusNode? findFirstFocusableChild(FocusNode node) => _findFirstFocusableChild(node);

  FocusNode? _findFirstFocusableChild(FocusNode node) {
    for (final FocusNode child in node.children) {
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

  /// 获取 [FocusNode] 所属的 [FocusTraversalGroup] 的 policy 实例。
  ///
  /// 通过 [FocusTraversalGroup.maybeOf] 查询节点 context 所在的 group。
  /// 返回 null 表示节点没有 context 或没有祖先 group。
  /// 两个节点如果返回相同的 policy 实例（[identical]），则它们在同一 group。
  FocusTraversalPolicy? _groupPolicyOf(FocusNode node) {
    final BuildContext? ctx = node.context;
    if (ctx == null) return null;
    return FocusTraversalGroup.maybeOf(ctx);
  }

  /// 判断两个 [FocusNode] 是否属于不同的 [FocusTraversalGroup]。
  bool _isCrossGroup(FocusNode a, FocusNode b) {
    final FocusTraversalPolicy? policyA = _groupPolicyOf(a);
    final FocusTraversalPolicy? policyB = _groupPolicyOf(b);
    if (policyA == null || policyB == null) return false;
    return !identical(policyA, policyB);
  }

  /// 方向键入口：检测跨 [FocusTraversalGroup] 边界的移动并触发三层降级。
  ///
  /// 采用方案 A：自行实现方向键几何排序，在排序结果上检测是否跨 group。
  /// 这样完全避免 super 污染 [FocusScopeNode.focusedChild] 记忆的问题。
  ///
  /// 策略：
  /// 1. 确定基准节点（[FocusScopeNode.focusedChild] 优先，否则用 currentNode）。
  /// 2. 在 nearestScope 的 traversalDescendants 中，按方向过滤+几何排序找候选。
  /// 3. 若候选与基准跨 group：对候选的 scope 执行 [_smartRequestFocus]。
  /// 4. 若同 group：直接聚焦候选（保持几何就近）。
  /// 5. 若无候选：fallback 到 super.inDirection。
  @override
  bool inDirection(FocusNode currentNode, TraversalDirection direction) {
    final FocusScopeNode? scope = currentNode.nearestScope;
    if (scope == null) {
      return super.inDirection(currentNode, direction);
    }

    // 确定基准节点：优先用 focusedChild，否则用 currentNode
    final FocusNode? focusedChild = scope.focusedChild;
    final FocusNode anchor =
        (focusedChild != null && focusedChild.canRequestFocus)
            ? focusedChild
            : currentNode;

    // 按方向做几何过滤+排序，找候选目标
    final FocusNode? candidate =
        _findDirectionalCandidate(scope, anchor, direction);

    if (candidate != null) {
      if (_isCrossGroup(anchor, candidate)) {
        // 跨 group：对候选的 scope 执行三层降级
        final FocusScopeNode? targetScope = candidate.nearestScope;
        if (targetScope != null) {
          return _smartRequestFocus(targetScope);
        }
      }
      // 同 group：直接聚焦候选（几何就近）
      candidate.requestFocus();
      return true;
    }

    // 无候选（例如已在边缘）：交给 super 处理边缘情况
    return super.inDirection(currentNode, direction);
  }

  /// 在 scope 的可聚焦节点中，按 [direction] 方向做几何排序找候选。
  ///
  /// 简化版几何就近算法：
  /// - 过滤掉基准节点本身和 rect 为零的节点。
  /// - 按方向过滤（只保留方向轴上"前方"的节点）。
  /// - 在方向轴上取距离基准最近的节点。
  FocusNode? _findDirectionalCandidate(
    FocusScopeNode scope,
    FocusNode anchor,
    TraversalDirection direction,
  ) {
    final Rect anchorRect = anchor.rect;
    if (anchorRect.isEmpty) return null;

    final List<FocusNode> nodes = scope.traversalDescendants
        .where((FocusNode node) =>
            node.canRequestFocus && node != anchor && !node.rect.isEmpty)
        .toList();

    if (nodes.isEmpty) return null;

    FocusNode? best;
    double bestPrimary = double.infinity; // 方向轴上的距离
    double bestSecondary = double.infinity; // 正交轴上的距离

    for (final FocusNode node in nodes) {
      final Rect r = node.rect;
      final bool forward;
      final double primary; // 方向轴上的距离
      final double secondary; // 正交轴上的距离

      switch (direction) {
        case TraversalDirection.right:
          forward = r.center.dx > anchorRect.center.dx;
          primary = (r.center.dx - anchorRect.center.dx).abs();
          secondary = (r.center.dy - anchorRect.center.dy).abs();
          break;
        case TraversalDirection.left:
          forward = r.center.dx < anchorRect.center.dx;
          primary = (r.center.dx - anchorRect.center.dx).abs();
          secondary = (r.center.dy - anchorRect.center.dy).abs();
          break;
        case TraversalDirection.down:
          forward = r.center.dy > anchorRect.center.dy;
          primary = (r.center.dy - anchorRect.center.dy).abs();
          secondary = (r.center.dx - anchorRect.center.dx).abs();
          break;
        case TraversalDirection.up:
          forward = r.center.dy < anchorRect.center.dy;
          primary = (r.center.dy - anchorRect.center.dy).abs();
          secondary = (r.center.dx - anchorRect.center.dx).abs();
          break;
      }

      if (!forward) continue;

      // 选方向轴距离最小的；若相同，选正交轴距离最小的
      if (primary < bestPrimary ||
          (primary == bestPrimary && secondary < bestSecondary)) {
        best = node;
        bestPrimary = primary;
        bestSecondary = secondary;
      }
    }

    return best;
  }

  /// Tab / shift+Tab 排序委托给 [_orderedPolicy]（走 [FocusTraversalOrder] 顺序）。
  @override
  Iterable<FocusNode> sortDescendants(
    Iterable<FocusNode> descendants,
    FocusNode currentNode,
  ) {
    return _orderedPolicy.sortDescendants(descendants, currentNode);
  }

  /// 清空指定 scope 的记忆（调试浮层"重置记忆"按钮触发）。
  ///
  /// 调用 [FocusNode.unfocus] 让 [FocusScopeNode.focusedChild] 回到 null，
  /// 从而强制下次进入时重新走第 2 层优先级逻辑，方便反复验证场景 1。
  void resetMemory(FocusScopeNode scope) {
    scope.focusedChild?.unfocus();
  }
}
