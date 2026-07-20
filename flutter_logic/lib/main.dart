import 'package:flutter/material.dart';
import 'claudeui/claude_ui_demo_page.dart';
import 'claudeui/nes_home_page.dart';
import 'codexui/codex_ui_demo_page.dart';
import 'doudouui/doudou_home_page.dart';
import 'doudouui/study_page.dart';
import 'gamepad_app/portrait_page.dart';
import 'home_page.dart';
import 'pages/personal_center_page.dart';

/// 启动参数：`flutter run --dart-define=initialPage=<route>` 快捷进入指定 playground 页。
/// 不传时默认 [HomePage]（playground 列表），用户点击进入；传了则直接打开该路由
/// （HomePage 仍在导航栈底，可返回）。例：`--dart-define=initialPage=/gamepad-portrait`
const String _kInitialPage = String.fromEnvironment(
  'initialPage',
  defaultValue: '',
);

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Playground',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        primarySwatch: Colors.blue,
        // 全局关闭 M3 scrolledUnder 效果：默认 AppBar 在 body 内 Scrollable
        // 滚动时背景色会叠加色调（变深/泛紫），iOS 上表现为状态栏颜色变化。
        // 此处统一配置，避免每个含 SingleChildScrollView 的页面重复防御。
        appBarTheme: const AppBarTheme(
          scrolledUnderElevation: 0,
          surfaceTintColor: Colors.transparent,
          backgroundColor: Color(0xFFF6F2F8),
        ),
      ),
      home: const HomePage(),
      initialRoute: _kInitialPage.isEmpty ? null : _kInitialPage,
      routes: <String, WidgetBuilder>{
        '/focus-demo': (_) => const PersonalCenterDemoPage(),
        codexUiRoute: (_) => const CodexUiDemoPage(),
        claudeUiRoute: (_) => const ClaudeUiDemoPage(),
        nesHomeRoute: (_) => const NesHomePage(),
        doudouHomeRoute: (_) => const DoudouHomePage(),
        doudouStudyRoute: (_) => const DoudouStudyPage(),
        gamepadPortraitRoute: (_) => const GamepadPortraitPage(),
      },
    );
  }
}
