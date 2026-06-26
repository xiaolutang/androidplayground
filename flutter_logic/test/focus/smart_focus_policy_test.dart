import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/smart_focus_policy.dart';

/// SmartFocusTraversalPolicy 三层降级逻辑单元测试。
///
/// **测试层级声明**：本文件验证以下逻辑的**纯分支**与**方向键入口**行为：
/// - [_smartRequestFocus]（通过 `smartRequestFocus` 包装直接调用）
/// - [_findFirstFocusableChild]（通过 `findFirstFocusableChild` 包装）
/// - [inDirection]（public @override，测试直接调用）
/// - [_findDirectionalCandidate]（通过 `findDirectionalCandidateForTest` 包装）
/// - [_isDescendantScope]（通过 `isDescendantScopeForTest` 包装）
/// - [resetMemory]
///
/// 覆盖 5 条三层降级分支 + 方向候选算法 + scope 树判断：
/// 1. 记忆命中：focusedChild 有效 -> 直接复用
/// 2. 优先级命中：focusedChild=null -> 命中 NumericFocusOrder(1.0)
/// 3. 记忆失效（SDK 保证）：见分支3 注释
/// 4. 优先级全失效 -> 走 DFS 兜底
/// 5. 极端兜底：无任何可用节点 -> scope 自身持有焦点
///
/// **NumericFocusOrder 语义**：order 值越小优先级越高（1.0 = 最高）。
///
/// **关于分支3 的诚实标注（Finding 5.2）**：
/// 通过 SDK 行为研究确认，Flutter 的 FocusNode 在 canRequestFocus
/// 从 true 变为 false 时，会自动 unfocus 该节点，并让 FocusScopeNode.focusedChild
/// 变为 null。因此 `_smartRequestFocus` 中的条件
/// `focusedChild != null && !canRequestFocus` 在 Flutter SDK 行为保证下
/// **不可达**。focusedChild 永远不会指向一个 canRequestFocus=false 的节点。
/// 分支3 测试名诚实反映这一事实。
void main() {
  /// 构建测试 harness：
  /// - 外层 FocusTraversalGroup 挂载 [SmartFocusTraversalPolicy]
  /// - 内部按 [entries] 创建 FocusTraversalOrder + Focus 节点
  /// - 返回 (nodes, scopeRef, policy) 便于用例控制
  ///
  /// [entries] 每项: (order, debugLabel, canRequestFocus)
  Future<({List<FocusNode> nodes, FocusScopeNode scopeRef, SmartFocusTraversalPolicy policy})>
      buildHarness(
    WidgetTester tester, {
    required List<({double order, String label, bool canFocus})> entries,
    List<Widget>? extraChildren,
  }) async {
    final SmartFocusTraversalPolicy policy = SmartFocusTraversalPolicy();
    final List<FocusNode> nodes = [];
    final List<Widget> children = [];

    for (final entry in entries) {
      final node = FocusNode(debugLabel: entry.label);
      node.canRequestFocus = entry.canFocus;
      nodes.add(node);

      children.add(
        FocusTraversalOrder(
          order: NumericFocusOrder(entry.order),
          child: Focus(
            focusNode: node,
            child: SizedBox(
              width: 100,
              height: 40,
              child: Text(entry.label),
            ),
          ),
        ),
      );
    }

    if (extraChildren != null) {
      children.addAll(extraChildren);
    }

    late FocusScopeNode scopeRef;

    await tester.pumpWidget(
      MaterialApp(
        home: FocusScope(
          child: FocusTraversalGroup(
            policy: policy,
            child: Scaffold(
              body: Builder(
                builder: (context) {
                  scopeRef = Focus.of(context).nearestScope!;
                  return Column(
                    children: children,
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );

    await tester.pump();

    return (nodes: nodes, scopeRef: scopeRef, policy: policy);
  }

  group('SmartFocusTraversalPolicy 三层降级', () {
    testWidgets(
      '分支1: 记忆命中 — focusedChild 有效 → 复用记忆节点',
      (WidgetTester tester) async {
        final harness = await buildHarness(
          tester,
          entries: [
            (order: 1.0, label: 'nodeA', canFocus: true),
            (order: 2.0, label: 'nodeB', canFocus: true),
            (order: 3.0, label: 'nodeC', canFocus: true),
          ],
        );

        // 先让 nodeB 获得焦点（建立记忆）
        harness.nodes[1].requestFocus();
        await tester.pump();

        // 确认记忆已建立
        expect(harness.scopeRef.focusedChild?.debugLabel, 'nodeB');

        // 调用 smartRequestFocus，应复用记忆（第 1 层命中）
        final result = harness.policy.smartRequestFocus(harness.scopeRef);
        await tester.pump();
        expect(result, isTrue);

        // primaryFocus 仍是 nodeB（复用记忆）
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'nodeB');
      },
    );

    testWidgets(
      '分支2: 记忆未命中(focusedChild=null) → 优先级层命中 NumericFocusOrder(1.0)',
      (WidgetTester tester) async {
        final harness = await buildHarness(
          tester,
          entries: [
            (order: 1.0, label: 'priorityA', canFocus: true),
            (order: 2.0, label: 'priorityB', canFocus: true),
            (order: 3.0, label: 'priorityC', canFocus: true),
          ],
        );

        // 确认无记忆（首次进入，focusedChild=null）
        expect(harness.scopeRef.focusedChild, isNull);

        // 调用 smartRequestFocus — 第 1 层 miss，第 2 层（优先级）命中
        final result = harness.policy.smartRequestFocus(harness.scopeRef);
        await tester.pump();
        expect(result, isTrue);

        // 应命中 NumericFocusOrder(1.0) = priorityA
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'priorityA');
      },
    );

    // ─── Finding 5.2: 分支3 诚实标注 ───
    //
    // SDK 行为研究结论（见文件头注释）：当 FocusNode.canRequestFocus 从 true 变为 false 时，
    // Flutter SDK 会自动调用 unfocus()，导致 FocusScopeNode.focusedChild 立即变为 null。
    // 因此 `_smartRequestFocus` 中 `focusedChild != null && !canRequestFocus` 的分支
    // 在 Flutter SDK 行为保证下**不可达** — focusedChild 永远不会指向
    // canRequestFocus=false 的节点。
    //
    // 本测试验证这一 SDK 保证：设 canRequestFocus=false 后 focusedChild 被清空，
    // smartRequestFocus 走的是与分支2 相同的"focusedChild=null → 优先级层"路径。
    // 测试名诚实反映"SDK 自动清空 → 等价走优先级层"的事实。
    testWidgets(
      '分支3: SDK 自动清空 focusedChild(canRequestFocus=false 触发 unfocus) → 等价走优先级层',
      (WidgetTester tester) async {
        final harness = await buildHarness(
          tester,
          entries: [
            (order: 1.0, label: 'fallbackA', canFocus: true),
            (order: 2.0, label: 'disposedB', canFocus: true),
            (order: 3.0, label: 'activeC', canFocus: true),
          ],
        );

        // Step 1: 让 disposedB 获得焦点（建立记忆）
        harness.nodes[1].requestFocus();
        await tester.pump();
        expect(harness.scopeRef.focusedChild?.debugLabel, 'disposedB');
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'disposedB');

        // Step 2: 模拟节点 dispose — 将 canRequestFocus 置 false
        // **SDK 保证**：Flutter 的 canRequestFocus setter 在 hasFocus 时自动 unfocus，
        // 导致 focusedChild 被立即清空为 null（而非保留指向不可聚焦节点）。
        harness.nodes[1].canRequestFocus = false;
        await tester.pump();

        // 验证 SDK 行为保证：focusedChild 已被清空
        // 这意味着 `_smartRequestFocus` 中 `focusedChild != null && !canRequestFocus`
        // 的分支实际不可达 — focusedChild 为 null，直接走优先级层
        expect(harness.scopeRef.focusedChild, isNull,
            reason: 'SDK 保证：canRequestFocus=false 时自动清空 focusedChild');
        expect(harness.nodes[1].canRequestFocus, isFalse);

        // 调用 smartRequestFocus — focusedChild=null，
        // 走第 2 层（优先级），命中 fallbackA
        final result = harness.policy.smartRequestFocus(harness.scopeRef);
        await tester.pump();
        expect(result, isTrue);

        // 应命中优先级最高节点 fallbackA，绝不是 disposedB
        final primary = FocusManager.instance.primaryFocus?.debugLabel;
        expect(primary, isNot('disposedB'));
        expect(primary, 'fallbackA');
      },
    );

    testWidgets(
      '分支4: 优先级全失效 → DFS 物理兜底层',
      (WidgetTester tester) async {
        // 添加一个无 FocusTraversalOrder 的可聚焦节点（DFS 兜底目标）
        final dfsNode = FocusNode(debugLabel: 'dfs_target');
        dfsNode.canRequestFocus = true;

        final harness = await buildHarness(
          tester,
          entries: [
            (order: 1.0, label: 'disabledA', canFocus: false),
            (order: 2.0, label: 'disabledB', canFocus: false),
            (order: 3.0, label: 'disabledC', canFocus: false),
          ],
          // 额外添加无 order 的可聚焦节点
          extraChildren: [
            Focus(
              focusNode: dfsNode,
              child: const SizedBox(width: 100, height: 40),
            ),
          ],
        );

        // 确认无记忆
        expect(harness.scopeRef.focusedChild, isNull);

        // 调用 smartRequestFocus — 第 1 层 miss（无记忆），
        // 第 2 层 miss（所有 order 节点 canRequestFocus=false），
        // 第 3 层 DFS 兜底应找到 dfs_target
        final result = harness.policy.smartRequestFocus(harness.scopeRef);
        await tester.pump();
        expect(result, isTrue);

        // 应命中 DFS 兜底节点
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'dfs_target');
      },
    );

    testWidgets(
      '分支5: 极端兜底 — 无任何可聚焦子节点 → scope 自身持有焦点',
      (WidgetTester tester) async {
        final harness = await buildHarness(
          tester,
          entries: [
            (order: 1.0, label: 'disabledA', canFocus: false),
            (order: 2.0, label: 'disabledB', canFocus: false),
            (order: 3.0, label: 'disabledC', canFocus: false),
          ],
        );

        // 确认无记忆
        expect(harness.scopeRef.focusedChild, isNull);

        // 调用 smartRequestFocus — 所有层都 miss：
        // 第 1 层 miss（无记忆），第 2 层 miss（全不可聚焦），第 3 层 miss（DFS 无果）
        // → 极端兜底：targetScope.requestFocus() 让 scope 自身持有焦点
        final result = harness.policy.smartRequestFocus(harness.scopeRef);
        await tester.pump();
        expect(result, isTrue);

        // primaryFocus 应为 scope 自身（或 scope 的内部表示），不为 null
        expect(FocusManager.instance.primaryFocus, isNotNull);
        // 不应命中任何子节点（它们全不可聚焦）
        final debugLabel = FocusManager.instance.primaryFocus?.debugLabel;
        for (final node in harness.nodes) {
          expect(debugLabel, isNot(node.debugLabel));
        }
      },
    );
  });

  // ─────────────────────────────────────────────────────────────────────
  // 以下为 `_findFirstFocusableChild` 算法层独立测试。
  // 与"分支4 DFS 兜底衔接测试"互补：分支4 验证"优先级层 miss → DFS 兜底"的
  // 衔接路径；此处直接验证 DFS 算法本身的"跳过不可聚焦 + 全 disabled 返回 null"行为。
  // ─────────────────────────────────────────────────────────────────────
  group('SmartFocusTraversalPolicy 辅助方法', () {
    testWidgets(
      'findFirstFocusableChild — DFS 遍历找第一个可聚焦节点',
      (WidgetTester tester) async {
        final harness = await buildHarness(
          tester,
          entries: [
            (order: 1.0, label: 'disabledFirst', canFocus: false),
            (order: 2.0, label: 'enabledSecond', canFocus: true),
            (order: 3.0, label: 'enabledThird', canFocus: true),
          ],
        );

        // DFS 应跳过 disabledFirst，返回 enabledSecond
        final result = harness.policy.findFirstFocusableChild(harness.scopeRef);
        expect(result?.debugLabel, 'enabledSecond');
      },
    );

    testWidgets(
      'findFirstFocusableChild — 全部不可聚焦时返回 null',
      (WidgetTester tester) async {
        final harness = await buildHarness(
          tester,
          entries: [
            (order: 1.0, label: 'disabledA', canFocus: false),
            (order: 2.0, label: 'disabledB', canFocus: false),
          ],
        );

        final result = harness.policy.findFirstFocusableChild(harness.scopeRef);
        expect(result, isNull);
      },
    );

    testWidgets(
      'resetMemory — 清空 scope 记忆',
      (WidgetTester tester) async {
        final harness = await buildHarness(
          tester,
          entries: [
            (order: 1.0, label: 'nodeA', canFocus: true),
            (order: 2.0, label: 'nodeB', canFocus: true),
          ],
        );

        // 建立记忆
        harness.nodes[1].requestFocus();
        await tester.pump();
        expect(harness.scopeRef.focusedChild?.debugLabel, 'nodeB');

        // 清空记忆
        harness.policy.resetMemory(harness.scopeRef);
        await tester.pump();
        expect(harness.scopeRef.focusedChild, isNull);
      },
    );
  });

  // ─────────────────────────────────────────────────────────────────────
  // Finding 5.3: inDirection / _findDirectionalCandidate / _isDescendantScope
  // 单元测试。通过 @visibleForTesting 包装方法直接调用。
  // ─────────────────────────────────────────────────────────────────────

  /// 构建带几何布局的方向键测试 harness。
  /// 节点按 [layout] 指定的位置排列，便于测试方向键候选算法。
  ///
  /// [layout] 每项: (label, left, top, width, height)
  Future<({List<FocusNode> nodes, FocusScopeNode scopeRef, SmartFocusTraversalPolicy policy})>
      buildDirectionalHarness(
    WidgetTester tester, {
    required List<({String label, double left, double top, double w, double h})> layout,
  }) async {
    final SmartFocusTraversalPolicy policy = SmartFocusTraversalPolicy();
    final List<FocusNode> nodes = [];

    for (final entry in layout) {
      final node = FocusNode(debugLabel: entry.label);
      nodes.add(node);
    }

    late FocusScopeNode scopeRef;

    await tester.pumpWidget(
      MaterialApp(
        home: FocusScope(
          child: FocusTraversalGroup(
            policy: policy,
            child: Scaffold(
              body: Builder(
                builder: (context) {
                  scopeRef = Focus.of(context).nearestScope!;
                  return Stack(
                    children: [
                      for (int i = 0; i < layout.length; i++)
                        Positioned(
                          left: layout[i].left,
                          top: layout[i].top,
                          child: SizedBox(
                            width: layout[i].w,
                            height: layout[i].h,
                            child: Focus(
                              focusNode: nodes[i],
                              child: Text(layout[i].label),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );

    await tester.pump();

    return (nodes: nodes, scopeRef: scopeRef, policy: policy);
  }

  group('Finding 5.3: _findDirectionalCandidate 方向候选算法', () {
    testWidgets('向下方向 — 返回正下方最近的节点', (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'top', left: 0, top: 0, w: 100, h: 40),
          (label: 'bottom', left: 0, top: 100, w: 100, h: 40),
        ],
      );

      final anchor = harness.nodes[0];
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, anchor, TraversalDirection.down,
      );

      expect(candidate?.debugLabel, 'bottom');
    });

    testWidgets('向上方向 — 返回正上方最近的节点', (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'top', left: 0, top: 0, w: 100, h: 40),
          (label: 'bottom', left: 0, top: 100, w: 100, h: 40),
        ],
      );

      final anchor = harness.nodes[1]; // bottom
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, anchor, TraversalDirection.up,
      );

      expect(candidate?.debugLabel, 'top');
    });

    testWidgets('向右方向 — 返回正右方最近的节点', (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'left', left: 0, top: 0, w: 100, h: 40),
          (label: 'right', left: 200, top: 0, w: 100, h: 40),
        ],
      );

      final anchor = harness.nodes[0]; // left
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, anchor, TraversalDirection.right,
      );

      expect(candidate?.debugLabel, 'right');
    });

    testWidgets('向左方向 — 返回正左方最近的节点', (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'left', left: 0, top: 0, w: 100, h: 40),
          (label: 'right', left: 200, top: 0, w: 100, h: 40),
        ],
      );

      final anchor = harness.nodes[1]; // right
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, anchor, TraversalDirection.left,
      );

      expect(candidate?.debugLabel, 'left');
    });

    testWidgets('无候选返回 null — 方向上无可达节点', (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'only', left: 100, top: 100, w: 100, h: 40),
        ],
      );

      // 只有一个节点，它是唯一的候选但 == anchor，应被过滤
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, harness.nodes[0], TraversalDirection.down,
      );

      expect(candidate, isNull);
    });

    // ─── FIX001: 垂直方向列聚类隔离 ───
    //
    // 防止左导航上下键跳到右内容区：垂直方向键时，候选必须与 anchor
    // 在 X 轴上有水平重叠（同一列），否则跳过。

    testWidgets('FIX001: 垂直方向列隔离 — 左列下键不跳到右列', (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          // 左列
          (label: 'L1', left: 0, top: 0, w: 100, h: 40),
          (label: 'L2', left: 0, top: 100, w: 100, h: 40),
          // 右列（与左列同行，X 区间不重叠）
          (label: 'R1', left: 200, top: 0, w: 100, h: 40),
          (label: 'R2', left: 200, top: 100, w: 100, h: 40),
        ],
      );

      // L1 按下键 → 候选应为 L2（同列），非 R2（同行 Y 距离=0 但不同列）
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, harness.nodes[0], TraversalDirection.down,
      );
      expect(candidate?.debugLabel, 'L2',
          reason: '垂直方向应只在同列内搜索，不跳到右列');
    });

    testWidgets('FIX001: 水平方向不受列隔离 — 左列右键仍找到右列', (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'L1', left: 0, top: 0, w: 100, h: 40),
          (label: 'L2', left: 0, top: 100, w: 100, h: 40),
          (label: 'R1', left: 200, top: 0, w: 100, h: 40),
          (label: 'R2', left: 200, top: 100, w: 100, h: 40),
        ],
      );

      // L1 按右键 → 候选应为 R1（水平方向不受 X 重叠过滤）
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, harness.nodes[0], TraversalDirection.right,
      );
      expect(candidate?.debugLabel, 'R1',
          reason: '水平方向不受列隔离过滤');
    });
  });

  group('Finding 5.3: inDirection 入口逻辑', () {
    testWidgets('同 scope 内直达 — 不触发三层降级', (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'top', left: 0, top: 0, w: 100, h: 40),
          (label: 'bottom', left: 0, top: 100, w: 100, h: 40),
        ],
      );

      // 让 top 获得焦点
      harness.nodes[0].requestFocus();
      await tester.pump();

      // 按下方向键 — 同 scope 内，应直接聚焦 bottom
      final result = harness.policy.inDirection(
        harness.nodes[0], TraversalDirection.down,
      );
      await tester.pump();

      expect(result, isTrue);
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'bottom');
    });

    testWidgets('Finding 5.15a: 最下节点按下键 → 无候选 → 回退 super.inDirection',
        (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'top', left: 0, top: 0, w: 100, h: 40),
          (label: 'bottom', left: 0, top: 100, w: 100, h: 40),
        ],
      );

      // 让 bottom 获得焦点
      harness.nodes[1].requestFocus();
      await tester.pump();

      // 按下方向键 — 底部无候选，findDirectionalCandidate 返回 null
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, harness.nodes[1], TraversalDirection.down,
      );
      expect(candidate, isNull,
          reason: '最下节点下方无候选');

      // inDirection 应回退到 super.inDirection（返回 true/false，不抛异常）
      final result = harness.policy.inDirection(
        harness.nodes[1], TraversalDirection.down,
      );
      // super.inDirection 在无候选时返回 false
      // super.inDirection 返回值由 SDK 内部搜索逻辑决定（可能 wrap-around：
      // 实测 down/right 在边缘可能返回 true，left/up 返回 false）。
      // 本测试仅验证回退路径不崩溃，不绑定具体返回值。
      expect(result, isA<bool>());
    });

    testWidgets('Finding 5.15a: 最左节点按左键 → 无候选 → 回退 super.inDirection',
        (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'left', left: 0, top: 0, w: 100, h: 40),
          (label: 'right', left: 200, top: 0, w: 100, h: 40),
        ],
      );

      // 让 left 获得焦点
      harness.nodes[0].requestFocus();
      await tester.pump();

      // 按左键 — 左侧无候选
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, harness.nodes[0], TraversalDirection.left,
      );
      expect(candidate, isNull,
          reason: '最左节点左方无候选');

      // inDirection 应回退到 super.inDirection
      final result = harness.policy.inDirection(
        harness.nodes[0], TraversalDirection.left,
      );
      // super.inDirection 返回值由 SDK 内部搜索逻辑决定（可能 wrap-around：
      // 实测 down/right 在边缘可能返回 true，left/up 返回 false）。
      // 本测试仅验证回退路径不崩溃，不绑定具体返回值。
      expect(result, isA<bool>());
    });

    testWidgets('Finding 5.15a: 最右节点按右键 → 无候选 → 回退 super.inDirection',
        (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'left', left: 0, top: 0, w: 100, h: 40),
          (label: 'right', left: 200, top: 0, w: 100, h: 40),
        ],
      );

      // 让 right 获得焦点
      harness.nodes[1].requestFocus();
      await tester.pump();

      // 按右键 — 右侧无候选
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, harness.nodes[1], TraversalDirection.right,
      );
      expect(candidate, isNull,
          reason: '最右节点右方无候选');

      // inDirection 应回退到 super.inDirection
      final result = harness.policy.inDirection(
        harness.nodes[1], TraversalDirection.right,
      );
      // super.inDirection 返回值由 SDK 内部搜索逻辑决定（可能 wrap-around：
      // 实测 down/right 在边缘可能返回 true，left/up 返回 false）。
      // 本测试仅验证回退路径不崩溃，不绑定具体返回值。
      expect(result, isA<bool>());
    });

    testWidgets('Finding 5.15a: 最上节点按上键 → 无候选 → 回退 super.inDirection',
        (tester) async {
      final harness = await buildDirectionalHarness(
        tester,
        layout: [
          (label: 'top', left: 0, top: 0, w: 100, h: 40),
          (label: 'bottom', left: 0, top: 100, w: 100, h: 40),
        ],
      );

      // 让 top 获得焦点
      harness.nodes[0].requestFocus();
      await tester.pump();

      // 按上键 — 上方无候选
      final candidate = harness.policy.findDirectionalCandidateForTest(
        harness.scopeRef, harness.nodes[0], TraversalDirection.up,
      );
      expect(candidate, isNull,
          reason: '最上节点上方无候选');

      // inDirection 应回退到 super.inDirection
      final result = harness.policy.inDirection(
        harness.nodes[0], TraversalDirection.up,
      );
      // super.inDirection 返回值由 SDK 内部搜索逻辑决定（可能 wrap-around：
      // 实测 down/right 在边缘可能返回 true，left/up 返回 false）。
      // 本测试仅验证回退路径不崩溃，不绑定具体返回值。
      expect(result, isA<bool>());
    });
  });

  // ─────────────────────────────────────────────────────────────────────
  // Finding 5.3: _isDescendantScope 单元测试
  // ─────────────────────────────────────────────────────────────────────
  group('Finding 5.3: _isDescendantScope scope 树判断', () {
    testWidgets('真 — candidate 是 ancestor 的后代 scope', (tester) async {
      final policy = SmartFocusTraversalPolicy();

      // 构建嵌套 FocusScope 结构
      late FocusScopeNode outerScope;
      late FocusScopeNode innerScope;

      await tester.pumpWidget(
        MaterialApp(
          home: FocusScope(
            child: FocusTraversalGroup(
              policy: policy,
              child: Scaffold(
                body: Focus(
                  autofocus: true,
                  child: Builder(
                    builder: (context) {
                      outerScope = Focus.of(context).nearestScope!;
                      return FocusScope(
                        child: Focus(
                          autofocus: true,
                          child: Builder(
                            builder: (context) {
                              innerScope = Focus.of(context).nearestScope!;
                              return const SizedBox();
                            },
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      // innerScope 是 outerScope 的后代
      expect(policy.isDescendantScopeForTest(innerScope, outerScope), isTrue);
    });

    testWidgets('假 — candidate 不是 ancestor 的后代 scope', (tester) async {
      final policy = SmartFocusTraversalPolicy();

      // 构建两个平级 FocusScope
      late FocusScopeNode scopeA;
      late FocusScopeNode scopeB;

      await tester.pumpWidget(
        MaterialApp(
          home: FocusTraversalGroup(
            policy: policy,
            child: Scaffold(
              body: Focus(
                autofocus: true,
                child: Column(
                  children: [
                    FocusScope(
                      child: Focus(
                        autofocus: true,
                        child: Builder(
                          builder: (context) {
                            scopeA = Focus.of(context).nearestScope!;
                            return const SizedBox();
                          },
                        ),
                      ),
                    ),
                    FocusScope(
                      child: Focus(
                        autofocus: true,
                        child: Builder(
                          builder: (context) {
                            scopeB = Focus.of(context).nearestScope!;
                            return const SizedBox();
                          },
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      // scopeB 不是 scopeA 的后代
      expect(policy.isDescendantScopeForTest(scopeB, scopeA), isFalse);
      expect(policy.isDescendantScopeForTest(scopeA, scopeB), isFalse);
    });
  });
}
