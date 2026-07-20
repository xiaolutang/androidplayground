import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/gamepad_app/portrait_page.dart';
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('portrait @390x844', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const MaterialApp(debugShowCheckedModeBanner: false, home: GamepadPortraitPage()));
    await tester.runAsync(() async {
      await precacheImage(const AssetImage('assets/gamepad_app/bg.png'), tester.element(find.byType(GamepadPortraitPage)));
    });
    await tester.pump(); await tester.pump();
    await expectLater(find.byType(GamepadPortraitPage), matchesGoldenFile('portrait_full.png'));
  });
}
