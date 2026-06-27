import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/smart_focus_policy.dart';

/// R004-FF005 信号通道单元测试。
///
/// 验证 SmartFocusTraversalPolicy.blockedDirectionNotifier 在
/// inDirection 返回 false 前被正确写入受阻方向。
void main() {
  group('FF005 blockedDirectionNotifier', () {
    testWidgets(
        '[垂直写入时机] 焦点在顶部按钮按上键 → notifier.value == up（return false 前）',
        (tester) async {
      final policy = SmartFocusTraversalPolicy();
      final nodeA = FocusNode(debugLabel: 'A');
      final nodeB = FocusNode(debugLabel: 'B');
      addTearDown(() {
        nodeA.dispose();
        nodeB.dispose();
        policy.blockedDirectionNotifier.dispose();
      });
      await tester.pumpWidget(
        MaterialApp(
          home: FocusTraversalGroup(
            policy: policy,
            child: SizedBox(
              width: 200,
              height: 400,
              child: Column(
                children: [
                  Focus(focusNode: nodeA, child: const SizedBox(height: 50)),
                  Focus(focusNode: nodeB, child: const SizedBox(height: 50)),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 聚焦 A（顶部）
      nodeA.requestFocus();
      await tester.pumpAndSettle();
      expect(policy.blockedDirectionNotifier.value, isNull);

      // 按上键（边界，无候选）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();

      // 断言 notifier 被写入 up（在 return false 之前）
      expect(
        policy.blockedDirectionNotifier.value,
        TraversalDirection.up,
        reason: '垂直方向无候选时应在 return false 前写入 up',
      );
    });

    testWidgets(
        '[水平写入时机] 焦点在最左按钮按左键 → notifier.value == left',
        (tester) async {
      final policy = SmartFocusTraversalPolicy();
      final nodeL = FocusNode(debugLabel: 'L');
      final nodeR = FocusNode(debugLabel: 'R');
      addTearDown(() {
        nodeL.dispose();
        nodeR.dispose();
        policy.blockedDirectionNotifier.dispose();
      });
      await tester.pumpWidget(
        MaterialApp(
          home: FocusTraversalGroup(
            policy: policy,
            child: Row(
              children: [
                Focus(focusNode: nodeL, child: const SizedBox(width: 50)),
                Focus(focusNode: nodeR, child: const SizedBox(width: 50)),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      nodeL.requestFocus();
      await tester.pumpAndSettle();

      // 按左键（最左，super 也找不到候选）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      await tester.pump();

      expect(
        policy.blockedDirectionNotifier.value,
        TraversalDirection.left,
        reason: '水平方向 super 无候选时应写入 left',
      );
    });

    testWidgets(
        '[正常路径不写入] 有候选时 notifier.value 保持 null',
        (tester) async {
      final policy = SmartFocusTraversalPolicy();
      final nodeA = FocusNode(debugLabel: 'A');
      final nodeB = FocusNode(debugLabel: 'B');
      addTearDown(() {
        nodeA.dispose();
        nodeB.dispose();
        policy.blockedDirectionNotifier.dispose();
      });
      await tester.pumpWidget(
        MaterialApp(
          home: FocusTraversalGroup(
            policy: policy,
            child: SizedBox(
              width: 200,
              height: 400,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Focus(
                      focusNode: nodeA,
                      child: const SizedBox(height: 50, width: double.infinity)),
                  Focus(
                      focusNode: nodeB,
                      child: const SizedBox(height: 50, width: double.infinity)),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      nodeA.requestFocus();
      await tester.pumpAndSettle();

      // 按下键（A→B 有候选，焦点正常切换）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();

      expect(
        policy.blockedDirectionNotifier.value,
        isNull,
        reason: '正常焦点切换时 notifier 不应被写入',
      );
    });

    testWidgets(
        '[reset 行为] 消费方置 null 后再次按键能重新写入',
        (tester) async {
      final policy = SmartFocusTraversalPolicy();
      final nodeA = FocusNode(debugLabel: 'A');
      addTearDown(() {
        nodeA.dispose();
        policy.blockedDirectionNotifier.dispose();
      });
      await tester.pumpWidget(
        MaterialApp(
          home: FocusTraversalGroup(
            policy: policy,
            child: Focus(focusNode: nodeA, child: const SizedBox()),
          ),
        ),
      );
      await tester.pumpAndSettle();

      nodeA.requestFocus();
      await tester.pumpAndSettle();

      // 第一次按上键写入 up
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      expect(policy.blockedDirectionNotifier.value, TraversalDirection.up);

      // 消费方置 null（模拟 FocusableButton._handleBlocked 的 reset）
      policy.blockedDirectionNotifier.value = null;

      // 再次按上键
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      expect(
        policy.blockedDirectionNotifier.value,
        TraversalDirection.up,
        reason: 'reset 后再次受阻应能重新写入',
      );
    });
  });
}
