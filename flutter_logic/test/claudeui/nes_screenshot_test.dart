import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/claudeui/nes_home_page.dart';

/// Offline rasterization of the NES home page at its native 844x390 size.
/// Run: flutter test --update-goldens test/claudeui/nes_screenshot_test.dart
Future<void> main() async {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Register the bundled typeface so labels match the Figma source.
  Future<void> loadF(String path) async {
    final ByteData data = await rootBundle.load(path);
    final FontLoader loader = FontLoader('AlibabaPuHuiTi')
      ..addFont(Future<ByteData>.value(data));
    await loader.load();
  }

  await loadF('fonts/Alibaba-PuHuiTi-Regular.otf');
  await loadF('fonts/Alibaba-PuHuiTi-Bold.otf');
  await loadF('fonts/Alibaba-PuHuiTi-Heavy.otf');

  testWidgets('nes home golden @844x390', (tester) async {
    tester.view.physicalSize = const Size(844, 390);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: NesHomePage(),
      ),
    );

    // Several raster images decode async — precache each inside runAsync.
    await tester.runAsync(() async {
      final BuildContext el = tester.element(find.byType(NesHomePage));
      for (final String p in <String>[
        'assets/claudeui/nes/bg.png',
        'assets/claudeui/nes/nes_console_full.png',
        'assets/claudeui/nes/nes_title.png',
        'assets/claudeui/nes/topbar.png',
        'assets/claudeui/nes/tabs2.png',
        'assets/claudeui/nes/dock.png',
        'assets/claudeui/nes/card_nes.png',
        'assets/claudeui/nes/card_sens.png',
        'assets/claudeui/nes/card_gb.png',
        'assets/claudeui/nes/card_gbc.png',
        'assets/claudeui/nes/card_gba.png',
      ]) {
        await precacheImage(AssetImage(p), el);
      }
    });
    await tester.pump();
    await tester.pump();

    await expectLater(
      find.byType(NesHomePage),
      matchesGoldenFile('nes_home.png'),
    );
  });
}
