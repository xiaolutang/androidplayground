import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/doudouui/study_page.dart';

/// 离线渲染豆豆思维课时页 @375x836，锁定 Flutter 端视觉回归基准。
/// Run: flutter test --update-goldens test/doudouui/study_screenshot_test.dart
Future<void> main() async {
  TestWidgetsFlutterBinding.ensureInitialized();

  await (FontLoader('AlibabaPuHuiTi')
        ..addFont(rootBundle.load('fonts/Alibaba-PuHuiTi-Regular.otf'))
        ..addFont(rootBundle.load('fonts/Alibaba-PuHuiTi-Bold.otf'))
        ..addFont(rootBundle.load('fonts/Alibaba-PuHuiTi-Heavy.otf')))
      .load();

  testWidgets('doudou study golden @375x836', (tester) async {
    tester.view.physicalSize = const Size(375, 836);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: DoudouStudyPage(),
      ),
    );

    // 图片异步解码需在 runAsync 里 precache。
    await tester.runAsync(() async {
      final BuildContext el = tester.element(find.byType(DoudouStudyPage));
      for (final String p in <String>[
        'assets/doudouui/study/status_signal.png',
        'assets/doudouui/study/subject_ip.png',
        'assets/doudouui/study/subject_highlight.png',
        'assets/doudouui/study/prep_advisor.png',
        'assets/doudouui/study/prep_remind.png',
        'assets/doudouui/study/arrow.png',
        'assets/doudouui/study/course_icon_base.png',
        'assets/doudouui/study/stamp.png',
        'assets/doudouui/study/current_bg.png',
        'assets/doudouui/study/current_cover.png',
        'assets/doudouui/study/lock.png',
        'assets/doudouui/study/weekly_icon.png',
        'assets/doudouui/study/banner_ball.png',
        'assets/doudouui/study/banner_star.png',
        'assets/doudouui/study/banner_role.png',
        'assets/doudouui/study/progress_node.png',
        'assets/doudouui/study/tab_learn.png',
        'assets/doudouui/study/tab_task.png',
        'assets/doudouui/study/tab_square.png',
        'assets/doudouui/study/tab_read.png',
        'assets/doudouui/study/tab_mine.png',
      ]) {
        await precacheImage(AssetImage(p), el);
      }
    });
    await tester.pump();
    await tester.pump();

    await expectLater(
      find.byType(DoudouStudyPage),
      matchesGoldenFile('doudou_study.png'),
    );
  });
}
