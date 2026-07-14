import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/focusable_button.dart';

import 'focus_test_helpers.dart';

/// R004-FB008 FocusableButton 抖动反馈单元测试。
///
/// 验证订阅 notifier 后的方向感知抖动、防抖重启、非焦点不抖、dispose 无 leak。
void main() {
  group('FB008 FocusableButton shake', () {
    testWidgets(
        '[方向感知垂直] primaryFocus + 收到 up → Transform.translate.dy 振荡, dx=0',
        (tester) async {
      final notifier = ValueNotifier<TraversalDirection?>(null);
      addTearDown(() => notifier.dispose());

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: FocusableButton(
                label: 'A',
                autofocus: true,
                blockedNotifier: notifier,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 确保 A 持有焦点
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'A',
          reason: '测试前置：A 应通过 autofocus 获得焦点');

      // 触发受阻信号
      notifier.value = TraversalDirection.up;

      // 验证 controller 已启动
      final state = tester.state(find.byType(FocusableButton)) as dynamic;
      final controller = state.shakeControllerForTest as AnimationController;
      expect(controller.isAnimating, isTrue, reason: '受阻信号后 controller 应启动动画');

      // 先 pump 一帧让 Ticker 启动，再推进时间
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 30));

      final translate = getTranslateOffset(tester, 'A');

      expect(translate.dy, isNot(equals(0.0)), reason: '垂直受阻时 dy 应振荡非零');
      expect(translate.dx, equals(0.0), reason: '垂直受阻时 dx 应保持 0');

      // 等待抖动结束
      await tester.pumpAndSettle();
      final translateAfter = getTranslateOffset(tester, 'A');
      // sin(6π) 浮点尾差约 -2e-15，用距离 < 0.01 判定归零
      expect(translateAfter.distance, lessThan(0.01),
          reason: '抖动结束后 Transform.translate 应归零（浮点尾差容忍）');
    });

    testWidgets(
        '[方向感知水平] primaryFocus + 收到 left → Transform.translate.dx 振荡, dy=0',
        (tester) async {
      final notifier = ValueNotifier<TraversalDirection?>(null);
      addTearDown(() => notifier.dispose());

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: FocusableButton(
                label: 'A',
                autofocus: true,
                blockedNotifier: notifier,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      notifier.value = TraversalDirection.left;
      // 先 pump 一帧让 Ticker 启动，再推进时间
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 30));

      final translate = getTranslateOffset(tester, 'A');
      expect(translate.dx, isNot(equals(0.0)), reason: '水平受阻时 dx 应振荡非零');
      expect(translate.dy, equals(0.0), reason: '水平受阻时 dy 应保持 0');
    });

    testWidgets('[非焦点不抖] 非 primaryFocus 收到信号 → Transform 保持 0', (tester) async {
      final notifier = ValueNotifier<TraversalDirection?>(null);
      addTearDown(() => notifier.dispose());

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: Column(
                children: [
                  FocusableButton(
                    label: 'Focused',
                    autofocus: true,
                    blockedNotifier: notifier,
                  ),
                  FocusableButton(
                    label: 'Idle',
                    blockedNotifier: notifier,
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Idle 按钮非 primaryFocus
      notifier.value = TraversalDirection.up;
      await tester.pump(const Duration(milliseconds: 30));

      final translate = getTranslateOffset(tester, 'Idle');
      expect(translate, equals(Offset.zero),
          reason: '非 primaryFocus 按钮收到信号不应抖动');
    });

    testWidgets('[防抖重启] 动画中再次收到信号 → forward(from:0) 重启', (tester) async {
      final notifier = ValueNotifier<TraversalDirection?>(null);
      addTearDown(() => notifier.dispose());

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: FocusableButton(
                label: 'A',
                autofocus: true,
                blockedNotifier: notifier,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final state = tester.state(find.byType(FocusableButton)) as dynamic;
      final controller = state.shakeControllerForTest as AnimationController;

      // 第一次触发
      notifier.value = TraversalDirection.up;
      // 先 pump 一帧让 Ticker 启动，再推进时间
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 30));
      expect(controller.isAnimating, isTrue);
      final progress1 = controller.value;
      expect(progress1, greaterThan(0));

      // 推进到更晚
      await tester.pump(const Duration(milliseconds: 100));
      final progressMid = controller.value;

      // 再次触发（需先 reset null 再写 up）
      notifier.value = null;
      notifier.value = TraversalDirection.up;
      await tester.pump(const Duration(milliseconds: 5));

      // controller 应从接近 0 重新开始（from:0 重启）
      expect(controller.value, lessThan(progressMid),
          reason: '防抖应 forward(from:0) 重启，value 应小于重启前的进度');
      expect(controller.isAnimating, isTrue);
    });

    testWidgets(
        '[dispose 无 leak] widget unmount → controller.dispose + removeListener',
        (tester) async {
      final notifier = ValueNotifier<TraversalDirection?>(null);
      addTearDown(() => notifier.dispose());

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: FocusableButton(
                label: 'A',
                autofocus: true,
                blockedNotifier: notifier,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final state = tester.state(find.byType(FocusableButton)) as dynamic;
      expect(state.isDisposed, isFalse);

      // unmount
      await tester.pumpWidget(const MaterialApp(home: Scaffold()));
      await tester.pumpAndSettle();

      // notifier 不再有 listener：设值不会触发已 dispose 的回调
      // （若 listener 未移除，会触发 "used after dispose" 断言）
      notifier.value = TraversalDirection.up;
      await tester.pump();
      // 无异常即通过
    });
  });
}
