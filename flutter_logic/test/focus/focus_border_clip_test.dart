import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';
import 'package:flutter_logic/focus/focusable_button.dart';

/// FocusableButton 焦点 border 左右被裁剪回归测试。
///
/// 根因：Border.all(width:2) 画在按钮 rect 边界中心，外侧 1px 外延。
/// 按钮在 Column(stretch) 下撑满 SingleChildScrollView viewport 宽度，
/// border 外延被 Clip.hardEdge 裁掉。
///
/// 修复：FocusableButton 的 AnimatedContainer 加 margin:horizontal:2，
/// 按钮内缩，border 外延不超出 viewport。
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('[iPhone16-横屏] 焦点按钮 border 左右不被裁', (tester) async {
    const Size logicalSize = Size(844, 390);
    tester.view.physicalSize = logicalSize * 3.0;
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
    await tester.pumpAndSettle();

    // 跨到右内容区：右键到会员签到
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, '会员签到');

    final Finder btn = find.widgetWithText(FocusableButton, '会员签到');
    final Finder scrollFinder = find.byType(SingleChildScrollView);
    // border 画在 AnimatedContainer 内部的 DecoratedBox 上（margin 内缩后），
    // 不是 FocusableButton 根 rect（外层 Padding 撑满宽度）。
    final Finder decorated = find.descendant(
      of: btn,
      matching: find.byType(DecoratedBox),
    ).first;
    final Rect borderRect = tester.getRect(decorated);
    final Rect scrollRect = tester.getRect(scrollFinder);

    // 按钮内缩：DecoratedBox（border 所在）左右不贴 scroll viewport 边缘
    // border 外延 1px 需在 viewport 内：borderRect.left > scrollRect.left 且
    // borderRect.right < scrollRect.right（margin 至少留出 border 外延空间）
    expect(
      borderRect.left > scrollRect.left,
      isTrue,
      reason: 'border 左边应内缩，外延不被左裁。'
          'borderLeft=${borderRect.left}, scrollLeft=${scrollRect.left}',
    );
    expect(
      borderRect.right < scrollRect.right,
      isTrue,
      reason: 'border 右边应内缩，外延不被右裁。'
          'borderRight=${borderRect.right}, scrollRight=${scrollRect.right}',
    );
  });
}
