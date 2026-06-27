import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:flutter_logic/main.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';

/// 在真实模拟器跑，焦点下移每步截图到 /tmp/sb_step_N.png。
/// 截图后由外部脚本分析状态栏区域像素变化。
///
/// 必须用 MyApp() 而非裸 MaterialApp：appBarTheme 全局关闭 M3 scrolledUnder，
/// 若用裸 MaterialApp 则测试环境与生产环境不一致，scrolledUnder 仍触发，
/// 状态栏闪烁问题在这个测试里根本测不到。
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('焦点下移截图序列', (tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();

    // 进入个人中心页（MyApp 的 home 是 HomePage，需点击入口跳转）
    await tester.tap(find.text('Flutter 焦点 Demo'));
    await tester.pumpAndSettle();
    expect(find.byType(PersonalCenterDemoPage), findsOneWidget);

    // 回归守卫：appBarTheme 必须配置（否则 scrolledUnder 会触发状态栏闪烁）
    final AppBarTheme appBarTheme =
        Theme.of(tester.element(find.byType(AppBar))).appBarTheme;
    expect(appBarTheme.scrolledUnderElevation, 0);
    expect(appBarTheme.surfaceTintColor, Colors.transparent);
    expect(appBarTheme.backgroundColor, const Color(0xFFF6F2F8));

    Future<void> snap(int n) async {
      final List<int> raw = await IntegrationTestWidgetsFlutterBinding
          .instance
          .takeScreenshot('sb_step_$n');
      final Uint8List bytes = Uint8List.fromList(raw);
      final File f = File('/tmp/sb_step_$n.png');
      await f.writeAsBytes(bytes);
      // ignore: avoid_print
      print('SAVED /tmp/sb_step_$n.png (${bytes.length} bytes)');
    }

    await snap(0);

    final keys = <LogicalKeyboardKey>[
      LogicalKeyboardKey.arrowDown, // 设置
      LogicalKeyboardKey.arrowDown, // 关于
      LogicalKeyboardKey.arrowRight, // 会员签到
      LogicalKeyboardKey.arrowDown, // 账户信息
      LogicalKeyboardKey.arrowDown, // 我的钱包
      LogicalKeyboardKey.arrowDown, // 消息中心
      LogicalKeyboardKey.arrowDown, // 退出登录
    ];

    for (var i = 0; i < keys.length; i++) {
      await tester.sendKeyEvent(keys[i]);
      await tester.pumpAndSettle();
      await snap(i + 1);
    }
  });
}
