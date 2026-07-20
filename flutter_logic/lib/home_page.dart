import 'package:flutter/material.dart';
import 'claudeui/claude_ui_demo_page.dart';
import 'claudeui/nes_home_page.dart';
import 'codexui/codex_ui_demo_page.dart';
import 'doudouui/doudou_home_page.dart';
import 'doudouui/study_page.dart';
import 'gamepad_app/portrait_page.dart';

/// Playground 总入口页（R003-HM001）
///
/// ListView 列出所有 demo 入口。新增 demo 时：
/// 1. 在 [_demos] 加一条 `(title, route)`
/// 2. 在 `main.dart` 的 `routes` 注册对应路由
class HomePage extends StatelessWidget {
  const HomePage({super.key});

  /// demo 入口清单。新增 demo 时在此追加即可。
  static const List<({String title, String route})> _demos =
      <({String title, String route})>[
    (title: 'Flutter 焦点 Demo', route: '/focus-demo'),
    (title: '[Codex] 手柄贴图还原', route: codexUiRoute),
    (title: '[Claude] gamepad 手柄还原', route: claudeUiRoute),
    (title: '[Claude] NES 首页还原', route: nesHomeRoute),
    (title: '豆豆首页还原 Demo', route: doudouHomeRoute),
    (title: '[Claude] 豆豆思维课时页', route: doudouStudyRoute),
    (title: '[Claude] 竖版手柄(DPad)', route: gamepadPortraitRoute),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Playground')),
      body: ListView.builder(
        itemCount: _demos.length,
        itemBuilder: (BuildContext context, int index) {
          final demo = _demos[index];
          return ListTile(
            title: Text(demo.title),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.pushNamed(context, demo.route),
          );
        },
      ),
    );
  }
}
