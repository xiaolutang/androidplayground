import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';

import 'focus_test_helpers.dart';

/// R004-FF009 端到端集成测试。
///
/// 真实加载 PersonalCenterDemoPage（非 mock），通过 sendKeyEvent 触发完整链路：
/// SDK → policy.inDirection → notifier 写入 → FocusableButton 订阅 → 抖动。
void main() {
  group('R004 端到端受阻抖动', () {
    testWidgets(
        '[垂直边界] 会员签到按上键 → dy 振荡 + 焦点不变',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
      await tester.pumpAndSettle();

      // 焦点初始在"个人中心"（autofocus），导航到右内容区"会员签到"
      await _navigateToButton(tester, '会员签到');
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, '会员签到');

      // 按上键（边界，垂直方向无候选）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 30));

      // 抖动中：dy 振荡非零，dx=0
      final translate = getTranslateOffset(tester, '会员签到');
      expect(translate.dy, isNot(equals(0.0)),
          reason: '垂直边界受阻时 dy 应振荡非零');
      expect(translate.dx, equals(0.0),
          reason: '垂直边界受阻时 dx 应保持 0');

      // 等待抖动结束
      await tester.pumpAndSettle();
      final translateAfter = getTranslateOffset(tester, '会员签到');
      expect(translateAfter.distance, lessThan(0.01),
          reason: '抖动结束后 Transform 应归零');

      // 焦点仍在会员签到
      expect(FocusManager.instance.primaryFocus?.debugLabel, '会员签到',
          reason: '边界受阻时焦点不变');
    });

    testWidgets(
        '[水平边界] 个人中心按左键 → dx 振荡',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
      await tester.pumpAndSettle();

      // "个人中心"已 autofocus
      expect(FocusManager.instance.primaryFocus?.debugLabel, '个人中心');

      // 按左键（最左，无候选）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 30));

      final translate = getTranslateOffset(tester, '个人中心');
      expect(translate.dx, isNot(equals(0.0)),
          reason: '水平边界受阻时 dx 应振荡非零');
      expect(translate.dy, equals(0.0),
          reason: '水平边界受阻时 dy 应保持 0');
    });

    testWidgets(
        '[连续防抖] 连按 3 次上键（80ms 间隔）→ 无堆叠',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
      await tester.pumpAndSettle();

      await _navigateToButton(tester, '会员签到');
      await tester.pumpAndSettle();

      // 连续 3 次，间隔 80ms
      for (int i = 0; i < 3; i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 80));
      }

      // 抖动应仍在进行（最后一次重启后 80ms）
      // 无堆叠：controller 只有一个实例，不会创建多个
      // 验证方式：抖动平滑，焦点仍不变
      expect(FocusManager.instance.primaryFocus?.debugLabel, '会员签到',
          reason: '连续防抖期间焦点不变');

      // 等待最后一次抖动自然结束
      await tester.pumpAndSettle();
      final translateAfter = getTranslateOffset(tester, '会员签到');
      expect(translateAfter.distance, lessThan(0.01),
          reason: '连续防抖结束后 Transform 应归零');
    });

    testWidgets(
        '[失焦取消] 抖动中按下键切换焦点 → 原按钮停止抖动',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
      await tester.pumpAndSettle();

      await _navigateToButton(tester, '会员签到');
      await tester.pumpAndSettle();

      // 启动抖动（按上键）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 30));

      // 抖动中
      final translateDuring = getTranslateOffset(tester, '会员签到');
      expect(translateDuring.dy, isNot(equals(0.0)),
          reason: '抖动应已启动');

      // 按下键切换焦点到"账户信息"
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 10));

      // 原按钮（会员签到）抖动应已停止
      final translateAfter = getTranslateOffset(tester, '会员签到');
      expect(translateAfter.distance, lessThan(0.01),
          reason: '失焦后原按钮抖动应立即停止');

      // 焦点已切换到账户信息
      expect(FocusManager.instance.primaryFocus?.debugLabel, '账户信息',
          reason: '按下键后焦点应切换到账户信息');
    });
  });
}

/// 导航到指定按钮：从"个人中心"按右键进入右内容区，然后定位目标。
Future<void> _navigateToButton(WidgetTester tester, String label) async {
  // 按右键从左导航进入右内容区（触发三层降级 → 记忆/优先级层 → 会员签到）
  await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
  await tester.pumpAndSettle();
  // 默认进入后焦点在"会员签到"（NumericFocusOrder(1.0) 最小）
  // 如需其他按钮，需额外的上下键导航
  if (label != '会员签到') {
    final target = _findFocusByLabel(label);
    target.requestFocus();
    await tester.pumpAndSettle();
  }
}

FocusNode _findFocusByLabel(String label) {
  // 通过 primaryFocus 所在的 FocusTraversalGroup 的 descendants 查找
  // 简化：直接用 FocusManager 找到 debugLabel 匹配的节点
  final primary = FocusManager.instance.primaryFocus!;
  FocusScopeNode? scope = primary.nearestScope;
  while (scope != null) {
    for (final node in scope.traversalDescendants) {
      if (node.debugLabel == label) return node;
    }
    scope = scope.enclosingScope;
  }
  return primary;
}

