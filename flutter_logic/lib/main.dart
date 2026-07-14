import 'package:flutter/material.dart';
import 'claudeui/claude_ui_demo_page.dart';
import 'claudeui/nes_home_page.dart';
import 'codexui/codex_ui_demo_page.dart';
import 'doudouui/doudou_home_page.dart';
import 'home_page.dart';
import 'pages/personal_center_page.dart';

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
      routes: <String, WidgetBuilder>{
        '/focus-demo': (_) => const PersonalCenterDemoPage(),
        codexUiRoute: (_) => const CodexUiDemoPage(),
        claudeUiRoute: (_) => const ClaudeUiDemoPage(),
        nesHomeRoute: (_) => const NesHomePage(),
        doudouHomeRoute: (_) => const DoudouHomePage(),
      },
    );
  }
}
