import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/gamepad_app/portrait_page.dart';
import 'package:flutter_logic/gamepad_app/view/layer/focus_ring.dart';
import 'package:flutter_logic/gamepad_app/view/layer/menu_card.dart';
import 'package:flutter_logic/gamepad_app/view/menu_overlay.dart';

const List<MenuItem> _items = <MenuItem>[
  MenuItem(
    action: MenuAction.quickSave,
    title: '快速存档',
    icon: 'assets/gamepad_app/ic_load.svg',
    caption: '覆盖快速存档',
  ),
  MenuItem(
    action: MenuAction.quitGame,
    title: '退出游戏',
    icon: 'assets/gamepad_app/ic_quit.svg',
  ),
  MenuItem(
    action: MenuAction.saveManagement,
    title: '存档管理',
    icon: 'assets/gamepad_app/ic_cundang.svg',
    caption: '3/3 已用',
  ),
  MenuItem(
    action: MenuAction.speed,
    title: '倍速',
    icon: 'assets/gamepad_app/ic_beisu.svg',
  ),
  MenuItem(
    action: MenuAction.quickLoad,
    title: '快速读档',
    icon: 'assets/gamepad_app/ic_save.svg',
    caption: '14:32',
  ),
  MenuItem(
    action: MenuAction.continueGame,
    title: '继续游戏',
    icon: 'assets/gamepad_app/ic_jixu.svg',
    caption: '返回游戏',
    initiallyFocused: true,
  ),
];

Future<void> main() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  await (FontLoader('AlibabaPuHuiTi')
        ..addFont(rootBundle.load('fonts/Alibaba-PuHuiTi-Regular.otf'))
        ..addFont(rootBundle.load('fonts/Alibaba-PuHuiTi-Heavy.otf')))
      .load();

  testWidgets('menu state golden @390x844', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: GamepadPortraitPage(),
      ),
    );
    await tester.runAsync(() async {
      await precacheImage(
        const AssetImage('assets/gamepad_app/bg.png'),
        tester.element(find.byType(GamepadPortraitPage)),
      );
    });
    await tester.tap(
      find.byKey(const ValueKey<String>('gamepad-menu-toggle')),
    );
    await tester.pumpAndSettle();

    expect(find.byType(MenuOverlay), findsOneWidget);
    await expectLater(
      find.byType(GamepadPortraitPage),
      matchesGoldenFile('menu_overlay.png'),
    );
  });

  testWidgets('all six cards are reachable and activation follows focus',
      (WidgetTester tester) async {
    MenuAction? selected;
    bool closed = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 390,
            height: 844,
            child: MenuOverlay(
              items: _items,
              onClose: () => closed = true,
              onSelected: (MenuAction action) => selected = action,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(MenuCard), findsNWidgets(6));
    expect(find.byType(FocusRing), findsOneWidget);

    Future<void> activate(
      MenuAction expected, {
      LogicalKeyboardKey? move,
    }) async {
      if (move != null) {
        await tester.sendKeyEvent(move);
        await tester.pump();
      }
      expect(find.byType(FocusRing), findsOneWidget);
      selected = null;
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected, expected);
    }

    await activate(MenuAction.continueGame);
    await activate(MenuAction.quickLoad, move: LogicalKeyboardKey.arrowLeft);
    await activate(
      MenuAction.saveManagement,
      move: LogicalKeyboardKey.arrowUp,
    );
    await activate(MenuAction.quickSave, move: LogicalKeyboardKey.arrowUp);
    await activate(MenuAction.quitGame, move: LogicalKeyboardKey.arrowRight);
    await activate(MenuAction.speed, move: LogicalKeyboardKey.arrowDown);
    await activate(
      MenuAction.continueGame,
      move: LogicalKeyboardKey.arrowDown,
    );

    await tester.tapAt(const Offset(10, 500));
    await tester.pump();
    expect(closed, isTrue);
  });

  testWidgets('logo remains above mask and toggles the menu closed',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: GamepadPortraitPage()),
    );
    final Finder toggle =
        find.byKey(const ValueKey<String>('gamepad-menu-toggle'));

    await tester.tap(toggle);
    await tester.pump();
    expect(find.byType(MenuOverlay), findsOneWidget);

    await tester.tap(toggle);
    await tester.pump();
    expect(find.byType(MenuOverlay), findsNothing);
  });
}
