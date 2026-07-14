import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/claudeui/claude_ui_demo_page.dart';

/// Offline rasterization of the gamepad overlay at its native 844x390 size,
/// so the reproduction can be compared pixel-for-pixel against the Figma export.
/// Run: flutter test --update-goldens test/claudeui/screenshot_test.dart
///
/// Notes on the two async-timing workarounds:
/// * The background image decodes on the real async timeline, which the fake
///   clock used by `pump` does not advance — so we precache it inside
///   `runAsync` (real wall-clock time passes) and avoid `pumpAndSettle`.
/// * Custom fonts declared in pubspec are not reliably picked up by the test
///   runner, so we register the bundled Alibaba PuHuiTi Heavy via FontLoader.
Future<void> main() async {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Register the bundled typeface so the pill labels match the Figma source.
  Future<void> loadF(String path) async {
    final ByteData data = await rootBundle.load(path);
    final FontLoader loader = FontLoader('AlibabaPuHuiTi')
      ..addFont(Future<ByteData>.value(data));
    await loader.load();
  }

  await loadF('fonts/Alibaba-PuHuiTi-Regular.otf');
  await loadF('fonts/Alibaba-PuHuiTi-Bold.otf');
  await loadF('fonts/Alibaba-PuHuiTi-Heavy.otf');

  testWidgets('gamepad overlay golden @844x390', (tester) async {
    tester.view.physicalSize = const Size(844, 390);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: GamepadOverlay(),
      ),
    );

    // Precache the background image so it has decoded before we capture.
    await tester.runAsync(() async {
      await precacheImage(
        const AssetImage('assets/claudeui/bg.png'),
        tester.element(find.byType(GamepadOverlay)),
      );
    });
    await tester.pump();
    await tester.pump();

    await expectLater(
      find.byType(GamepadOverlay),
      matchesGoldenFile('claudeui_overlay.png'),
    );
  });
}
