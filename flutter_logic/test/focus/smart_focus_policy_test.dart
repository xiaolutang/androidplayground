import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/smart_focus_policy.dart';

/// SmartFocusTraversalPolicy 三层降级逻辑单元测试。
///
/// 覆盖 5 条分支：
/// 1. 记忆命中：focusedChild 有效 → 直接复用
/// 2. 优先级命中：focusedChild=null → 命中 NumericFocusOrder(1.0)
/// 3. 记忆失效：focusedChild 对应节点 dispose / canRequestFocus=false → 跳过记忆走优先级
/// 4. 优先级全失效 → 走 DFS 兜底
/// 5. 极端兜底：无任何可用节点 → scope 自身持有焦点
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

    testWidgets(
      '分支3: 记忆失效(focusedChild 节点 canRequestFocus=false) → 跳过记忆走优先级层',
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
        // Flutter 的 canRequestFocus setter 在 hasFocus 时自动 unfocus，
        // 导致 focusedChild 被清除（模拟 dispose 后的记忆失效）
        harness.nodes[1].canRequestFocus = false;
        await tester.pump();

        // 验证 disposedB 确实已失效
        expect(harness.nodes[1].canRequestFocus, isFalse);

        // 调用 smartRequestFocus — 记忆层（focusedChild）失效或为 null，
        // 应跳过记忆，走优先级层
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
}
