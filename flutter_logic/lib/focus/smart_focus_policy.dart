import 'package:flutter/widgets.dart';

/// 自定义焦点遍历策略：记忆 > 优先级 > 物理兜底三层降级。
///
/// 挂在 [FocusTraversalGroup.policy] 上，方向键触发时被 Flutter 焦点系统回调。
///
/// ## 触发机制（R002-FB007 修复后）
///
/// Flutter SDK 方向键的实际调用链：
/// 1. `FocusNode.focusInDirection()` →
///    `FocusTraversalGroup.of(context).inDirection(this, direction)`
/// 2. `FocusTraversalGroup.of(context)` 返回**最近**祖先 group 的 policy
///
/// **关键**：为了让方向键跨区域工作，整个页面应共用一个 [FocusTraversalGroup]
/// （挂载本 policy），子区域用 [FocusScope] 隔离记忆但**不**各自创建独立 group。
/// 这样 `FocusTraversalGroup.of()` 始终返回本 policy，`nearestScope` 包含
/// 所有区域的节点，方向键候选搜索能跨越区域边界。
///
/// 本类重写 [inDirection] 来拦截方向键事件：
/// - 先在方向轴上做几何排序找候选目标节点。
/// - 检查候选是否与当前焦点跨越了 [FocusScope] 边界。
/// - 若**跨 scope**：对目标 scope 执行三层降级（记忆>优先级>兜底）。
/// - 若**同 scope 内**：直接聚焦候选，保持几何就近。
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

  /// 判断 [candidate] scope 是否是 [ancestor] scope 的后代。
  ///
  /// 用于区分方向键移动方向：
  /// - 从外层 scope 向内层 scope 移动（如左导航→右内容区）：
  ///   候选 scope 是 startScope 的后代 → 触发三层降级
  /// - 从内层 scope 向外层 scope 移动（如右内容区→左导航）：
  ///   候选 scope 不是 startScope 的后代 → 直接聚焦候选
  ///
  /// @visibleForTesting 包装见 [isDescendantScopeForTest]。
  bool _isDescendantScope(FocusScopeNode candidate, FocusScopeNode ancestor) {
    FocusNode? node = candidate.parent;
    while (node != null) {
      if (identical(node, ancestor)) return true;
      node = node.parent;
    }
    return false;
  }

  /// 方向键入口：检测跨 [FocusScope] 边界的移动并触发三层降级。
  ///
  /// 策略：
  /// 1. 确定基准节点（[FocusScopeNode.focusedChild] 优先，否则用 currentNode）。
  /// 2. 从 nearestScope 开始，逐级向上搜索父 scope 的 traversalDescendants，
  ///    按方向过滤+几何排序找候选。这确保跨 scope（如左导航↔右内容区）的方向键
  ///    能找到目标区域的节点。
  /// 3. 若候选与基准跨 scope：对候选的 scope 执行 [_smartRequestFocus]（记忆>优先级>兜底）。
  /// 4. 若同 scope：直接聚焦候选（保持几何就近）。
  /// 5. 若无候选（所有层级都找不到）：fallback 到 super.inDirection。
  @override
  bool inDirection(FocusNode currentNode, TraversalDirection direction) {
    final FocusScopeNode? startScope = currentNode.nearestScope;
    if (startScope == null) {
      return super.inDirection(currentNode, direction);
    }

    // 确定基准节点：优先用 focusedChild，否则用 currentNode
    final FocusNode? focusedChild = startScope.focusedChild;
    final FocusNode anchor =
        (focusedChild != null && focusedChild.canRequestFocus)
            ? focusedChild
            : currentNode;

    // 从 nearestScope 开始逐级向上搜索候选
    // 这保证跨 scope 的方向键能找到目标区域的节点
    FocusScopeNode? scope = startScope;
    while (scope != null) {
      final FocusNode? candidate =
          _findDirectionalCandidate(scope, anchor, direction);

      if (candidate != null) {
        final FocusScopeNode? candidateScope = candidate.nearestScope;
        if (candidateScope != null &&
            candidateScope != startScope &&
            _isDescendantScope(candidateScope, startScope)) {
          // 候选在 startScope 的子 scope 中（如左导航→右内容区）：
          // 对候选的 scope 执行三层降级（记忆>优先级>兜底）
          return _smartRequestFocus(candidateScope);
        }
        // 同 scope 或候选在祖先 scope（如右内容区→左导航）：
        // 直接聚焦候选（几何就近），不走三层降级
        candidate.requestFocus();
        return true;
      }

      // 当前 scope 内无候选，向上到父 scope 继续搜索
      // enclosingScope 会跳过非 scope 的中间 FocusNode，
      // 直接找到祖先链中的下一个 FocusScopeNode
      scope = scope.enclosingScope;
    }

    // 所有层级都无候选（例如已在边缘）：交给 super 处理边缘情况
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

      // 列聚类：垂直方向键时，只保留与 anchor 在 X 轴上有水平重叠的候选。
      // 防止左导航上下键跳到右内容区（同行 Y 距离=0 会胜出同列下一行）。
      // 用区间相交判断（非中心点），宽窄不同的按钮也能正确聚类。
      if (direction == TraversalDirection.up ||
          direction == TraversalDirection.down) {
        if (r.left >= anchorRect.right || r.right <= anchorRect.left) {
          continue;
        }
      }

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

  // ─────────────────────────────────────────────────────────────────────
  // 以下为 @visibleForTesting 包装方法，仅用于单元测试直接调用
  // _findDirectionalCandidate / _isDescendantScope（私有方法）。
  // inDirection 本身已是 public @override，测试可直接调用，无需包装。
  // 不改策略逻辑，仅暴露内部方法给测试断言。
  // ─────────────────────────────────────────────────────────────────────

  /// @visibleForTesting 包装：调用 [_findDirectionalCandidate]。
  @visibleForTesting
  FocusNode? findDirectionalCandidateForTest(
    FocusScopeNode scope,
    FocusNode anchor,
    TraversalDirection direction,
  ) =>
      _findDirectionalCandidate(scope, anchor, direction);

  /// @visibleForTesting 包装：调用 [_isDescendantScope]。
  @visibleForTesting
  bool isDescendantScopeForTest(
          FocusScopeNode candidate, FocusScopeNode ancestor) =>
      _isDescendantScope(candidate, ancestor);

  /// 清空指定 scope 的记忆（调试浮层"重置记忆"按钮触发）。
  ///
  /// 调用 [FocusNode.unfocus] 让 [FocusScopeNode.focusedChild] 回到 null，
  /// 从而强制下次进入时重新走第 2 层优先级逻辑，方便反复验证场景 1。
  void resetMemory(FocusScopeNode scope) {
    scope.focusedChild?.unfocus();
  }
}
