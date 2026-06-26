import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/focus/focusable_button.dart';

/// FocusableButton（FF004）widget 测试。
///
/// 覆盖 4 条验收场景 + Finding 5.9/5.10/5.15b 补强：
/// 1. 高亮态：获得焦点 → Container 边框为蓝色 + AnimatedScale 终态 scale = 1.05
/// 2. 非高亮态：失去焦点 → 边框透明 + scale = 1.0
/// 3. enabled=false → FocusNode.canRequestFocus=false（primaryFocus 不会落到此节点）
/// 4. 生命周期：widget unmount 后 FocusNode.dispose 被调用（通过 isDisposed 验证）
///
/// Finding 5.9: nodeOf Actions 干扰验证
/// Finding 5.10: 通过 state.isDisposed 真实验证 dispose 调用
/// Finding 5.15b: FF006 onTap 测试（tap + Enter key）
void main() {
  /// 用 MaterialApp + Scaffold 包裹，避免 Directionality / MediaQuery 等缺失。
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  /// 从当前 widget 树中取出 FocusableButton 内部的 FocusNode。
  ///
  /// FF004 实现把 `_focusNode` 赋给 [Focus.focusNode]，并令其 debugLabel = widget.label。
  /// 这里直接通过 widget 引用相等匹配 FocusableButton 内部的 Focus，
  /// 避免外层 FocusScope / Actions 引入的其他 Focus 节点干扰。
  ///
  /// **Finding 5.9 验证结论**：
  /// Flutter 的 [Actions] widget 内部**不**创建独立的 FocusNode，
  /// 它使用 [Actions.actionsKey] 来查找 Actions context，但不向 Focus 树
  /// 注入额外的 Focus widget。因此 `nodeOf` 的 `find.byWidgetPredicate`
  /// 按 `w is Focus && w.focusNode != null && w.focusNode!.debugLabel == label`
  /// 过滤**不会**匹配到 Actions 注入的节点。
  ///
  /// Actions 的实现（Flutter SDK）仅创建 `_ActionsMarker`（InheritedWidget），
  /// 不创建 Focus 子树。唯一可能干扰的场景是外层 [FocusScope] 的根 FocusNode，
  /// 但它的 debugLabel 为 null，不会被 label 过滤命中。
  ///
  /// `expect(focuses, hasLength(1))` 断言本身也是一种验证：
  /// 如果 Actions 注入了额外的 debugLabel 匹配节点，此断言会失败。
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

  // ─── Finding 5.10: 通过 state.isDisposed 真实验证 dispose 被调用 ───
  //
  // 原场景4 只断言 hasFocus=false + enclosingScope=null，验证的是 Flutter SDK 的
  // FocusNode.dispose 行为，即使 FF004 忘记调 `_focusNode.dispose()` 测试也可能通过。
  //
  // 现在通过 `_FocusableButtonState.isDisposed` getter 直接断言 State.dispose()
  // 内部的 `_disposed = true` 被执行。测试须在 unmount 前拿到 State 引用。
  testWidgets(
    '场景4: widget unmount 后 state.isDisposed=true，FocusNode.dispose 真正被调用',
    (WidgetTester tester) async {
      // 第一帧：挂载 FocusableButton，拿到 State 引用（unmount 后无法再获取）
      await tester.pumpWidget(
        wrap(FocusableButton(label: 'Transient')),
      );
      await tester.pump();

      final FocusNode node = nodeOf(tester, 'Transient');
      expect(node.canRequestFocus, isTrue); // 未 dispose 前为 true

      // 拿到 State 引用（unmount 前）
      final State<StatefulWidget> state = tester.state(
        find.byType(FocusableButton),
      );
      // 使用 dynamic 访问 isDisposed（@visibleForTesting getter）
      // ignore: avoid_dynamic_calls
      bool getIsDisposed(dynamic s) => s.isDisposed as bool;
      expect(getIsDisposed(state), isFalse,
          reason: 'unmount 前 isDisposed 应为 false');

      // 第二帧：替换为完全不相关的简化 widget 树 → 触发 State.dispose → _focusNode.dispose()
      await tester.pumpWidget(
        wrap(const SizedBox()),
      );
      await tester.pumpAndSettle();

      // Finding 5.10 核心断言：state.isDisposed 为 true
      // 这是直接验证 FF004 的 dispose() 被调用的证据，
      // 而非依赖 Flutter SDK FocusNode.dispose 的副作用。
      expect(getIsDisposed(state), isTrue,
          reason: 'unmount 后 state.isDisposed 必须为 true，'
              '证明 FF004 的 dispose() 内部 `_disposed = true` 被执行');

      // 原断言保留作为补充验证
      expect(node.hasFocus, isFalse,
          reason: 'dispose 后节点不应保留焦点状态');
      expect(node.enclosingScope, isNull,
          reason: 'dispose 后节点应已脱离任何 FocusScope');

      // 尝试在已 dispose 的节点上 requestFocus 不抛异常
      expect(() => node.requestFocus(), returnsNormally);
      expect(tester.takeException(), isNull);
    },
  );

  // ─── Finding 5.15b: FF006 onTap 测试 ───
  group('Finding 5.15b: FF006 onTap 回调', () {
    testWidgets(
      'tap 手势触发 onTap 回调',
      (WidgetTester tester) async {
        bool tapped = false;

        await tester.pumpWidget(
          wrap(FocusableButton(
            label: 'TapMe',
            onTap: () => tapped = true,
          )),
        );
        await tester.pump();

        // 确认初始状态
        expect(tapped, isFalse);

        // 模拟 tap 手势
        await tester.tap(find.byType(FocusableButton));
        await tester.pump();

        // 验证 onTap 被触发
        expect(tapped, isTrue);
      },
    );

    testWidgets(
      'Enter 键通过 ActivateIntent 触发 onTap 回调',
      (WidgetTester tester) async {
        bool tapped = false;

        await tester.pumpWidget(
          wrap(FocusableButton(
            label: 'EnterMe',
            onTap: () => tapped = true,
          )),
        );
        await tester.pump();

        // 先让按钮获得焦点
        final FocusNode node = nodeOf(tester, 'EnterMe');
        node.requestFocus();
        await tester.pumpAndSettle();

        expect(node.hasFocus, isTrue);
        expect(tapped, isFalse);

        // 模拟 Enter 键 → 通过 Actions(ActivateIntent) 触发 onTap
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pump();

        // 验证 onTap 被触发
        expect(tapped, isTrue,
            reason: 'Enter 键应通过 ActivateIntent → CallbackAction → onTap');
      },
    );

    testWidgets(
      'enabled=false 时 onTap 不被触发（tap 和 Enter 均无效）',
      (WidgetTester tester) async {
        bool tapped = false;

        await tester.pumpWidget(
          wrap(FocusableButton(
            label: 'Disabled',
            enabled: false,
            onTap: () => tapped = true,
          )),
        );
        await tester.pump();

        // tap 无效
        await tester.tap(find.byType(FocusableButton));
        await tester.pump();
        expect(tapped, isFalse, reason: 'disabled 按钮不应响应 tap');

        // Enter 无效（节点不可聚焦，无法获得焦点）
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pump();
        expect(tapped, isFalse, reason: 'disabled 按钮不应响应 Enter');
      },
    );
  });
}
