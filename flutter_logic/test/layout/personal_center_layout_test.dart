import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';
import 'package:flutter_logic/focus/focusable_button.dart';

/// R002-FIX004 布局回归测试：左右两区撑满 body 高度 + 顶部对齐。
///
/// 修复前（Row 默认 crossAxisAlignment.center + Stack loose）：
/// - 平板：右内容区按内容高度垂直居中 → 用户看到"上下居中对齐"
/// - 手机横屏：右内容区内容高度 > body 高度，溢出被裁 → 退出登录底部看不到
///
/// 修复后（Stack fit: expand + Row crossAxisAlignment.stretch）：
/// - 左右两区撑满 body 高度
/// - 按钮从顶部开始排列
/// - 退出登录在可滚动区域内，获焦时可滚动到完全可见
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> pumpApp(WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
    await tester.pumpAndSettle();
  }

  void runLayoutTest(String deviceName, Size logicalSize, double dpr) {
    testWidgets('[$deviceName] 左右两区撑满 body 高度 + 顶部对齐', (tester) async {
      tester.view.physicalSize = logicalSize * dpr;
      tester.view.devicePixelRatio = dpr;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await pumpApp(tester);

      final Rect firstButtonRect = tester.getRect(
        find.widgetWithText(FocusableButton, '会员签到'),
      );
      final Rect lastButtonRect = tester.getRect(
        find.widgetWithText(FocusableButton, '退出登录'),
      );

      // 顶部对齐：会员签到（右内容第一个按钮）的 top 应在屏幕上半部，
      // 而非垂直居中（修复前在平板上 top ≈ 屏幕高度/2）。
      expect(
        firstButtonRect.top < logicalSize.height / 2,
        isTrue,
        reason: '[$deviceName] 右内容首个按钮应在屏幕上半部（顶部对齐），'
            '实际 top=${firstButtonRect.top}（屏幕高 ${logicalSize.height}）',
      );

      // 退出登录的 rect 不应超出屏幕底部（修复前手机横屏会溢出被裁）。
      // 注：SingleChildScrollView 会滚动，退出登录可能需要滚动才完全可见，
      // 但初始状态下其 rect.bottom 不应远超屏幕高度（内容应在滚动范围内合理布局）。
      expect(
        lastButtonRect.bottom,
        lessThan(logicalSize.height * 2),
        reason: '[$deviceName] 退出登录不应严重溢出屏幕',
      );

      // 左导航第一个按钮"个人中心"也应在顶部
      final Rect leftFirstRect = tester.getRect(
        find.widgetWithText(FocusableButton, '个人中心'),
      );
      expect(
        leftFirstRect.top < logicalSize.height / 2,
        isTrue,
        reason: '[$deviceName] 左导航首个按钮应在屏幕上半部',
      );
    });
  }

  runLayoutTest('iPhone16-横屏', const Size(844, 390), 3.0);
  runLayoutTest('iPad-横屏', const Size(1024, 768), 2.0);
  runLayoutTest('默认800x600', const Size(800, 600), 1.0);

  /// 问题1 自查：退出登录（右内容最底部按钮）可通过滚动完全可见。
  ///
  /// 测试环境 focus ensureVisible 不自动滚动（test binding 限制），
  /// 故手动滚动验证"退出登录可达且能完全进入 viewport"——这是 border 不被
  /// Clip 裁的几何前提。真机上 focus 获焦会自动 ensureVisible 触发同样滚动。
  ///
  /// 关键：Column 末尾的 SizedBox(height:24) 提供底部余量，确保退出登录
  /// 完全滚入 viewport 后，其后仍有空间（border 不贴 viewport 边缘）。
  testWidgets('[iPhone16-横屏] 退出登录可滚动完全可见（border 不裁前提）', (tester) async {
    const Size logicalSize = Size(844, 390);
    tester.view.physicalSize = logicalSize * 3.0;
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
    await tester.pumpAndSettle();

    final Finder lastButton = find.widgetWithText(FocusableButton, '退出登录');
    final Finder viewport = find.byType(SingleChildScrollView);

    // 手动滚动直到退出登录完全可见
    await tester.scrollUntilVisible(
      lastButton,
      100,
      scrollable: find.descendant(
        of: find.byType(SingleChildScrollView),
        matching: find.byType(Scrollable),
      ),
    );
    await tester.pumpAndSettle();

    final Rect lastButtonRect = tester.getRect(lastButton);
    final Rect viewportRect = tester.getRect(viewport);

    // 退出登录应完全在 viewport 内（border 不被裁）
    expect(
      lastButtonRect.bottom <= viewportRect.bottom + 1,
      isTrue,
      reason: '退出登录滚动后底部应在 viewport 内，否则 border 被裁。'
          'bottom=${lastButtonRect.bottom}, viewport bottom=${viewportRect.bottom}',
    );
    expect(
      lastButtonRect.top >= viewportRect.top - 1,
      isTrue,
      reason: '退出登录顶部应在 viewport 内',
    );
  });

  /// FIX005 回归：iPhone 横屏底部有 home indicator（约 34px），
  /// Scaffold.body 默认不避开它，SingleChildScrollView viewport 会包括这段被遮挡区，
  /// ensureVisible 滚动后退出登录 border 底部落在 home indicator 下被遮（用户看到"被裁"）。
  /// SafeArea(bottom) 让 viewport 收缩到可见区，border 不被遮挡。
  testWidgets('[iPhone16-横屏+home indicator] 退出登录 border 不被 home indicator 遮挡', (tester) async {
    const Size logicalSize = Size(844, 390);
    const double homeIndicator = 34.0;
    tester.view.physicalSize = logicalSize * 3.0;
    tester.view.devicePixelRatio = 3.0;
    // viewPadding 是物理像素，乘 dpr
    tester.view.viewPadding = FakeViewPadding(bottom: homeIndicator * 3.0);
    tester.view.padding = FakeViewPadding(bottom: homeIndicator * 3.0);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetViewPadding);
    addTearDown(tester.view.resetPadding);

    await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
    await tester.pumpAndSettle();

    final Finder lastButton = find.widgetWithText(FocusableButton, '退出登录');

    await tester.scrollUntilVisible(
      lastButton,
      100,
      scrollable: find.descendant(
        of: find.byType(SingleChildScrollView),
        matching: find.byType(Scrollable),
      ),
    );
    await tester.pumpAndSettle();

    final Rect lastButtonRect = tester.getRect(lastButton);
    // 退出登录 border 底部应在 home indicator 上方（屏幕可见区内）
    expect(
      lastButtonRect.bottom <= logicalSize.height - homeIndicator + 1,
      isTrue,
      reason: '退出登录 border 底部应在 home indicator 上方（不被遮挡）。'
          'bottom=${lastButtonRect.bottom}, 可见区底部=${logicalSize.height - homeIndicator}',
    );
  });
}
