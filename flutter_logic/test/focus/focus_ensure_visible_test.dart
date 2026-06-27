import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';
import 'package:flutter_logic/focus/focusable_button.dart';

/// 跨 scope 方向键导航的 ensureVisible 回归测试（R002-FIX005）。
///
/// 验证 4 条 requestFocusCallback 路径（任何一条回归到 .requestFocus()
/// 都会让对应测试失败）：
///
/// - **优先级层**：首次跨 scope 进入右内容区（focusedChild=null），
///   OrderedTraversalPolicy 找 NumericFocusOrder 最小节点（会员签到）
/// - **记忆层**：跨 scope 离开再回来，focusedChild 命中（见下方专门用例）
/// - **同 scope 候选**：右内容区内 vertical 移动到底部按钮（见下方主用例）
/// - **物理兜底层**：所有按钮无 NumericFocusOrder 时走 DFS（已由
///   smart_focus_policy_test.dart 的 `_findFirstFocusableChild` 单测覆盖，
///   本文件不重复构造无 order 页面变体）
///
/// 根因（FIX005 修复前）：
/// 自定义 SmartFocusTraversalPolicy 的跨 scope 路径直接调用
/// candidate.requestFocus()，绕过了 requestFocusCallback hook，
/// 导致 SDK 内置的 ensureVisible 链路被切断，scrollOffset 保持 0，
/// 退出登录 bottom=383 超出 viewport(366) 被 Clip 裁 +
/// 被 home indicator(356) 遮挡。
///
/// FIX005：policy 层改用 requestFocusCallback(node, alignment:0.5)，
/// 恢复 SDK 的 ensureVisible 链路；alignment:0.5 强制居中以绕开
/// home indicator 安全区（SDK 默认 keepVisibleAtEnd 会落进 safe area）。
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  /// iPhone 16 横屏 + home indicator 的公共环境设置。
  /// 返回 logicalSize 供断言使用。
  Size setupIPhone16Landscape(WidgetTester tester) {
    const Size logicalSize = Size(844, 390);
    const double homeIndicator = 34.0;
    tester.view.physicalSize = logicalSize * 3.0;
    tester.view.devicePixelRatio = 3.0;
    tester.view.viewPadding = FakeViewPadding(bottom: homeIndicator * 3.0);
    tester.view.padding = FakeViewPadding(bottom: homeIndicator * 3.0);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetViewPadding);
    addTearDown(tester.view.resetPadding);
    return logicalSize;
  }

  /// 取右内容区 SingleChildScrollView 的 ScrollableState。
  ScrollableState rightScrollState(WidgetTester tester) {
    final Finder scrollable = find.descendant(
      of: find.byType(SingleChildScrollView),
      matching: find.byType(Scrollable),
    );
    return tester.state(scrollable);
  }

  testWidgets('[优先级层 + 同 scope 候选] 退出登录获焦后 ensureVisible 自动滚动', (tester) async {
    final Size logicalSize = setupIPhone16Landscape(tester);
    const double homeIndicator = 34.0;

    await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
    await tester.pumpAndSettle();

    // 真实方向键导航：个人中心 → 设置 → 右键跨 scope（优先级层） → 下键 ×4（同 scope 候选）到退出登录
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      '会员签到',
      reason: '首次跨 scope 走优先级层，应命中 NumericFocusOrder(1.0) 的会员签到',
    );
    for (int i = 0; i < 4; i++) {
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
    }

    expect(FocusManager.instance.primaryFocus?.debugLabel, '退出登录');

    final Finder lastButton = find.widgetWithText(FocusableButton, '退出登录');
    final ScrollableState scrollState = rightScrollState(tester);
    final Finder viewport = find.byType(SingleChildScrollView);

    // 关键断言1：focus 触发了 ensureVisible，scrollOffset > 0
    // 修复前 scrollOffset=0（系统不自动 ensureVisible），退出登录停在初始位置被裁
    expect(
      scrollState.position.pixels > 0,
      isTrue,
      reason: '退出登录获焦后应自动触发 Scrollable.ensureVisible 滚动。'
          'scrollOffset=${scrollState.position.pixels}',
    );

    final Rect lastRect = tester.getRect(lastButton);
    final Rect vpRect = tester.getRect(viewport);

    // 关键断言2：退出登录完全在 viewport 内（border 不被 Clip 裁）
    expect(
      lastRect.bottom <= vpRect.bottom + 1 && lastRect.top >= vpRect.top - 1,
      isTrue,
      reason: '退出登录应完全在 viewport 内。'
          'rect=$lastRect, viewport=$vpRect',
    );

    // 关键断言3：退出登录 border 不被 home indicator 遮挡
    expect(
      lastRect.bottom <= logicalSize.height - homeIndicator + 1,
      isTrue,
      reason: '退出登录 border 底部应在 home indicator 上方。'
          'bottom=${lastRect.bottom}, 可见区底部=${logicalSize.height - homeIndicator}',
    );
  });

  testWidgets('[记忆层] 跨 scope 离开再回来 → focusedChild 命中 + ensureVisible 恢复滚动', (tester) async {
    setupIPhone16Landscape(tester);

    await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
    await tester.pumpAndSettle();

    // 导航到退出登录（让右 scope.focusedChild = 退出登录的 FocusNode）
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    for (int i = 0; i < 4; i++) {
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
    }
    expect(FocusManager.instance.primaryFocus?.debugLabel, '退出登录');
    final double scrollBeforeLeave = rightScrollState(tester).position.pixels;
    expect(scrollBeforeLeave > 0, isTrue, reason: '前置：退出登录已滚动');

    // 左键跨 scope 回到左导航（focusedChild 仍记得退出登录）
    // 几何就近：退出登录 Y 与"关于"最近（都在底部），故命中"关于"
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pumpAndSettle();
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      '关于',
      reason: '左键回到左导航最底部（与退出登录 Y 相近）',
    );

    // **关键**：把 scrollOffset 重置为 0。
    // 这样若记忆层走 .requestFocus()（无 ensureVisible），scrollOffset 保持 0，
    // 测试失败；若走 requestFocusCallback（触发 ensureVisible），scrollOffset > 0。
    rightScrollState(tester).position.jumpTo(0);
    await tester.pumpAndSettle();
    expect(
      rightScrollState(tester).position.pixels,
      0,
      reason: '前置：手动重置 scrollOffset 为 0',
    );

    // 右键再次跨 scope：此时 rightScope.focusedChild=退出登录，应走记忆层
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();

    // 关键断言1：记忆层命中，焦点回到退出登录（而非重新走优先级层的会员签到）
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      '退出登录',
      reason: '记忆层应命中 focusedChild=退出登录，而非重新走优先级层到会员签到',
    );

    // 关键断言2：记忆层路径触发 ensureVisible，scrollOffset > 0
    // 回归捕获：修复前（记忆层走 .requestFocus()）scrollOffset 仍为 0，此断言失败。
    final double scrollAfterReturn = rightScrollState(tester).position.pixels;
    expect(
      scrollAfterReturn > 0,
      isTrue,
      reason: '记忆层 requestFocusCallback 应触发 Scrollable.ensureVisible，'
          '让退出登录滚回 viewport。若此断言失败说明记忆层回退到 .requestFocus()。',
    );

    // 关键断言3：退出登录在 viewport 内
    final Finder lastButton = find.widgetWithText(FocusableButton, '退出登录');
    final Finder viewport = find.byType(SingleChildScrollView);
    final Rect lastRect = tester.getRect(lastButton);
    final Rect vpRect = tester.getRect(viewport);
    expect(
      lastRect.bottom <= vpRect.bottom + 1 && lastRect.top >= vpRect.top - 1,
      isTrue,
      reason: '记忆层路径后退出登录应完全在 viewport 内。'
          'rect=$lastRect, viewport=$vpRect',
    );
  });
}
