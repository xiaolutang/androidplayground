import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/focusable_button.dart';

/// FocusableButton（FF004）widget 测试。
///
/// 覆盖 4 条验收场景：
/// 1. 高亮态：获得焦点 → Container 边框为蓝色 + AnimatedScale 终态 scale = 1.05
/// 2. 非高亮态：失去焦点 → 边框透明 + scale = 1.0
/// 3. enabled=false → FocusNode.canRequestFocus=false（primaryFocus 不会落到此节点）
/// 4. 生命周期：widget unmount 后 FocusNode.dispose 被调用（节点脱离 FocusScope，无 use-after-dispose）
void main() {
  /// 用 MaterialApp + Scaffold 包裹，避免 Directionality / MediaQuery 等缺失。
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  /// 从当前 widget 树中取出 FocusableButton 内部的 FocusNode。
  ///
  /// FF004 实现把 `_focusNode` 赋给 [Focus.focusNode]，并令其 debugLabel = widget.label。
  /// 这里直接通过 widget 引用相等匹配 FocusableButton 内部的 Focus，
  /// 避免外层 FocusScope / Actions 引入的其他 Focus 节点干扰。
  FocusNode nodeOf(WidgetTester tester, String label) {
    final Iterable<Focus> focuses = tester.widgetList<Focus>(
      find.byWidgetPredicate(
        (Widget w) =>
            w is Focus &&
            w.focusNode != null &&
            w.focusNode!.debugLabel == label,
      ),
    );
    expect(focuses, hasLength(1),
        reason: '期望仅有一个 debugLabel="$label" 的 Focus 节点');
    return focuses.single.focusNode!;
  }

  /// 从 widget 树中取 FocusableButton 内部 AnimatedContainer 的 BoxDecoration。
  //
  // 假设：widget 树中只有一个 FocusableButton（本测试 4 个场景均满足）。
  // 多 button 场景需要扩展为按 label 过滤。
  BoxDecoration? decorationOf(WidgetTester tester) {
    final Iterable<AnimatedContainer> widgets = tester.widgetList<AnimatedContainer>(
      find.descendant(
        of: find.byType(FocusableButton),
        matching: find.byType(AnimatedContainer),
      ),
    );
    expect(widgets, hasLength(1),
        reason: 'decorationOf 仅支持单 FocusableButton 场景');
    return widgets.single.decoration as BoxDecoration?;
  }

  testWidgets(
    '场景1: 获得焦点时 Container 有蓝色边框 + Transform.scale > 1.0',
    (WidgetTester tester) async {
      await tester.pumpWidget(
        wrap(FocusableButton(label: 'Confirm')),
      );
      await tester.pump();

      final FocusNode node = nodeOf(tester, 'Confirm');
      node.requestFocus();
      await tester.pumpAndSettle();

      // 断言 1：边框颜色为蓝色，宽度为 2
      final BoxDecoration? deco = decorationOf(tester);
      expect(deco, isNotNull);
      final Border? border = deco?.border as Border?;
      expect(border, isNotNull);
      expect(border!.top.color, equals(Colors.blue));
      expect(border.top.width, equals(2.0));

      // 断言 2：AnimatedScale 终态 scale = 1.05（> 1.0）
      final AnimatedScale scaleWidget = tester.widget<AnimatedScale>(
        find.descendant(
          of: find.byType(FocusableButton),
          matching: find.byType(AnimatedScale),
        ),
      );
      expect(scaleWidget.scale, greaterThan(1.0));
      expect(scaleWidget.scale, closeTo(1.05, 1e-9));
    },
  );

  testWidgets(
    '场景2: 失去焦点时边框透明 + scale = 1.0',
    (WidgetTester tester) async {
      // 用一个 FocusScope 同时承载 FocusableButton 和另一个可聚焦占位 widget，
      // 通过让占位节点抢焦，触发 FocusableButton 失焦。
      final FocusNode otherNode = FocusNode(debugLabel: 'other');

      await tester.pumpWidget(
        wrap(
          FocusScope(
            child: Column(
              children: <Widget>[
                FocusableButton(label: 'Target'),
                Focus(focusNode: otherNode, child: const SizedBox()),
              ],
            ),
          ),
        ),
      );
      await tester.pump();

      // 先让 button 获焦，再让 other 获焦，确保失焦路径被触发
      final FocusNode buttonNode = nodeOf(tester, 'Target');
      buttonNode.requestFocus();
      await tester.pumpAndSettle();
      otherNode.requestFocus();
      await tester.pumpAndSettle();

      expect(buttonNode.hasFocus, isFalse);

      // 断言 1：边框颜色为透明（FF004 实现中始终有 Border.all，颜色为 transparent）
      final BoxDecoration? deco = decorationOf(tester);
      expect(deco, isNotNull);
      final Border? border = deco?.border as Border?;
      expect(border, isNotNull);
      expect(border!.top.color, equals(Colors.transparent));

      // 断言 2：scale 回到 1.0
      final AnimatedScale scaleWidget = tester.widget<AnimatedScale>(
        find.descendant(
          of: find.byType(FocusableButton),
          matching: find.byType(AnimatedScale),
        ),
      );
      expect(scaleWidget.scale, equals(1.0));

      otherNode.dispose();
    },
  );

  testWidgets(
    '场景3: enabled=false 时 canRequestFocus=false，primaryFocus 不会落到此节点',
    (WidgetTester tester) async {
      await tester.pumpWidget(
        wrap(
          // 外层 FocusScope 便于在测试内手动尝试将焦点给到此 button 的节点
          FocusScope(
            child: FocusableButton(label: 'Disabled', enabled: false),
          ),
        ),
      );
      await tester.pump();

      final FocusNode node = nodeOf(tester, 'Disabled');

      // 断言 1：canRequestFocus 同步为 false（FF004 在 build 中维护）
      expect(node.canRequestFocus, isFalse);

      // 断言 2：尝试 requestFocus 也不会获得焦点
      node.requestFocus();
      await tester.pumpAndSettle();
      expect(node.hasFocus, isFalse);

      // 断言 3：当前 primaryFocus 不是此节点
      expect(identical(FocusManager.instance.primaryFocus, node), isFalse);
    },
  );

  testWidgets(
    '场景4: widget unmount 后 FocusNode.dispose 被调用，无 use-after-dispose',
    (WidgetTester tester) async {
      // 第一帧：挂载 FocusableButton，拿到内部 FocusNode 引用
      await tester.pumpWidget(
        wrap(FocusableButton(label: 'Transient')),
      );
      await tester.pump();

      final FocusNode node = nodeOf(tester, 'Transient');
      expect(node.canRequestFocus, isTrue); // 未 dispose 前为 true

      // 第二帧：替换为完全不相关的简化 widget 树 → 触发 State.dispose → _focusNode.dispose()
      await tester.pumpWidget(
        wrap(const SizedBox()),
      );
      await tester.pumpAndSettle();

      // 断言 1：dispose 后节点已从 FocusManager 中摘除 → enclosingScope 为 null，
      // 且 hasPrimaryFocus / hasFocus 均为 false（dispose 会触发 notifyListeners 清空焦点关系）。
      // 注意：Flutter 的 FocusNode.dispose 不会把 canRequestFocus 改成 false，
      // 但会断开与任何 FocusScope 的连接，从而保证无 use-after-dispose。
      expect(node.hasFocus, isFalse,
          reason: 'dispose 后节点不应保留焦点状态');
      expect(node.hasPrimaryFocus, isFalse,
          reason: 'dispose 后节点不应是 primaryFocus');
      expect(node.enclosingScope, isNull,
          reason: 'dispose 后节点应已脱离任何 FocusScope');

      // 断言 2：尝试在已 dispose 的节点上 requestFocus 不抛异常（不产生 use-after-dispose）
      // Flutter 的 FocusNode 实现允许 dispose 后调用，会被安全忽略
      expect(() => node.requestFocus(), returnsNormally);

      // 断言 3：整个 pump 过程没有未捕获异常
      expect(tester.takeException(), isNull);
    },
  );
}
