import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/codexui/codex_ui_demo_page.dart';
import 'package:flutter_logic/doudouui/doudou_home_page.dart';
import 'package:flutter_logic/main.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';

/// R003-HM003 入口页测试：
/// - 启动看到 Playground AppBar + 焦点 demo 入口项
/// - 点击入口跳到 PersonalCenterDemoPage（看到「个人中心」AppBar + 返回箭头）
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('入口页显示 Playground 标题 + 焦点 demo 入口', (tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();

    expect(find.text('Playground'), findsOneWidget);
    expect(find.text('Flutter 焦点 Demo'), findsOneWidget);
    expect(find.text('[Codex] 手柄贴图还原'), findsOneWidget);
    expect(find.text('[Claude] gamepad 手柄还原'), findsOneWidget);
    expect(find.text('[Claude] NES 首页还原'), findsOneWidget);
    expect(find.text('豆豆首页还原 Demo'), findsOneWidget);
    expect(find.text('[Claude] 豆豆思维课时页'), findsOneWidget);
    expect(find.text('[Claude] 竖版手柄(DPad)'), findsOneWidget);
    expect(find.byType(ListTile), findsNWidgets(7));
  });

  testWidgets('点击豆豆首页入口 → 跳到豆豆 Figma 首页', (tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('豆豆首页还原 Demo'));
    await tester.pumpAndSettle();

    expect(find.byType(DoudouHomePage), findsOneWidget);
    expect(find.byType(DoudouHomeCanvas), findsOneWidget);
    expect(find.text('绿豆豆乐园'), findsOneWidget);
    expect(find.text('模块名称'), findsOneWidget);
    expect(find.text('一行2个'), findsOneWidget);
    expect(find.text('一行3个'), findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (Widget widget) =>
            widget is Image &&
            widget.image is AssetImage &&
            (widget.image as AssetImage).assetName ==
                '${DoudouHomeCanvas.assetRoot}card_01.png' &&
            widget.fit == BoxFit.cover,
      ),
      findsWidgets,
    );
    expect(find.text('限免'), findsNWidgets(3));
    expect(find.text('订阅'), findsNWidgets(4));
    expect(find.text('更新'), findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (Widget widget) =>
            widget is Image &&
            widget.image is AssetImage &&
            (widget.image as AssetImage).assetName ==
                '${DoudouHomeCanvas.assetRoot}icon_lock.png',
      ),
      findsOneWidget,
    );

    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('点击焦点 demo 入口 → 跳到个人中心页（带返回箭头）', (tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Flutter 焦点 Demo'));
    await tester.pumpAndSettle();

    // 跳到 PersonalCenterDemoPage
    expect(find.byType(PersonalCenterDemoPage), findsOneWidget);
    // AppBar 标题是「个人中心」（注意：左导航按钮也有同名，故限定 AppBar 内）
    expect(
      find.descendant(of: find.byType(AppBar), matching: find.text('个人中心')),
      findsOneWidget,
    );

    // push 进栈时 AppBar 有返回箭头（手动 leading，ExcludeFocus 包裹）
    expect(find.byIcon(Icons.arrow_back), findsOneWidget);

    // R002 状态栏闪烁修复：AppBar 通过 appBarTheme 全局关闭 M3 scrolledUnder。
    // 三属性在 main.dart 的 appBarTheme 定义，body 滚动时不再让 AppBar 变色。
    final appBarTheme =
        Theme.of(tester.element(find.byType(AppBar))).appBarTheme;
    expect(
      appBarTheme.scrolledUnderElevation,
      0,
      reason: 'appBarTheme.scrolledUnderElevation 必须 0 关闭滚动叠加',
    );
    expect(
      appBarTheme.surfaceTintColor,
      Colors.transparent,
      reason: 'appBarTheme.surfaceTintColor 必须透明关闭 M3 tonal overlay',
    );
    expect(
      appBarTheme.backgroundColor,
      const Color(0xFFF6F2F8),
      reason: 'appBarTheme.backgroundColor 显式固定避免受 colorScheme 影响',
    );
  });

  testWidgets('点击 Codex UI 入口 → 跳到 Figma 还原页', (tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('[Codex] 手柄贴图还原'));
    await tester.pumpAndSettle();

    expect(find.byType(CodexUiDemoPage), findsOneWidget);
    expect(find.byType(CodexUiDesignFrame), findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (Widget widget) =>
            widget is Image &&
            widget.image is AssetImage &&
            (widget.image as AssetImage).assetName ==
                CodexUiDesignFrame.backgroundAsset &&
            widget.fit == BoxFit.fill &&
            widget.filterQuality == FilterQuality.low &&
            widget.isAntiAlias == false,
      ),
      findsOneWidget,
    );
  });

  /// AppBar 返回按钮用 ExcludeFocus 排除出焦点树，
  /// 方向键不应跨 scope 跳到它（避免干扰 SmartFocusTraversalPolicy 验证）。
  testWidgets('AppBar 返回按钮不参与方向键焦点导航', (tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Flutter 焦点 Demo'));
    await tester.pumpAndSettle();

    // 初始焦点在左导航个人中心（autofocus）
    expect(FocusManager.instance.primaryFocus?.debugLabel, '个人中心');

    // 按右键进入右内容区
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, '会员签到');

    // 按上键：会员签到是右内容区最顶，应停留，不跳到 AppBar back button
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
    await tester.pumpAndSettle();
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      '会员签到',
      reason: '右内容区顶部按上键应停留，不应跨 scope 跳到 AppBar 返回按钮',
    );
  });
}
