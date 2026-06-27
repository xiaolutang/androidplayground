import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_logic/focus/focusable_button.dart';

/// 焦点测试共享辅助函数（R004 收敛：消除 _getTranslateOffset 重复）。
///
/// 从 FocusableButton[label] 的 build 输出中读取 Transform.translate 的 offset。
/// 用于抖动反馈测试断言位移方向与幅度。
Offset getTranslateOffset(WidgetTester tester, String label) {
  final buttonFinder = find.widgetWithText(FocusableButton, label);
  final transformFinder = find.descendant(
    of: buttonFinder,
    matching: find.byType(Transform),
  );
  expect(transformFinder, findsOneWidget,
      reason: 'FocusableButton[$label] 应有一个 Transform 包裹');
  final transformWidget = tester.widget<Transform>(transformFinder);
  final t = transformWidget.transform.getTranslation();
  return Offset(t.x, t.y);
}
