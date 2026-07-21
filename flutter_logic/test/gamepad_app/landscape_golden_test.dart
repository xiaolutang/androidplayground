import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/gamepad_app/domain/models.dart';
import 'package:flutter_logic/gamepad_app/landscape_page.dart';
import 'package:flutter_logic/gamepad_app/view/layer/focus_ring.dart';
import 'package:flutter_logic/gamepad_app/view/layer/menu_card.dart';
import 'package:flutter_logic/gamepad_app/view/layout_switch_overlay.dart';
import 'package:flutter_logic/gamepad_app/view/menu_overlay.dart';

Future<void> main() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  await (FontLoader('AlibabaPuHuiTi')
        ..addFont(rootBundle.load('fonts/Alibaba-PuHuiTi-Regular.otf'))
        ..addFont(rootBundle.load('fonts/Alibaba-PuHuiTi-Heavy.otf')))
      .load();

  Future<void> pumpLandscape(
    WidgetTester tester, {
    ValueChanged<GamepadKey>? onKey,
    ValueChanged<MenuAction>? onMenuSelected,
    ValueChanged<GamepadLayout>? onLayoutSelected,
    bool showKeyLog = false,
    bool initialMenuOpen = false,
    bool initialLayoutOpen = false,
    GamepadLayout initialLayout = GamepadLayout.siliconePad,
  }) async {
    tester.view.physicalSize = const Size(844, 390);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        home: GamepadLandscapePage(
          onKey: onKey,
          onMenuSelected: onMenuSelected,
          onLayoutSelected: onLayoutSelected,
          showKeyLog: showKeyLog,
          initialMenuOpen: initialMenuOpen,
          initialLayoutOpen: initialLayoutOpen,
          initialLayout: initialLayout,
        ),
      ),
    );
    await tester.runAsync(() async {
      final BuildContext context =
          tester.element(find.byType(GamepadLandscapePage));
      await precacheImage(
        const AssetImage('assets/gamepad_app/bg.png'),
        context,
      );
    });
    await tester.pump();
    await tester.pump();
  }

  testWidgets('landscape matches the 844x390 Figma frame',
      (WidgetTester tester) async {
    await pumpLandscape(tester);

    await expectLater(
      find.byType(GamepadLandscapePage),
      matchesGoldenFile('landscape_full.png'),
    );
  });

  testWidgets('expand control hides and restores all operation clusters',
      (WidgetTester tester) async {
    await pumpLandscape(tester);

    expect(find.byKey(const ValueKey<String>('landscape-left-dpad')),
        findsOneWidget);
    expect(find.byKey(const ValueKey<String>('landscape-left-action-pad')),
        findsOneWidget);
    expect(find.byKey(const ValueKey<String>('landscape-right-action-pad')),
        findsOneWidget);
    expect(find.byKey(const ValueKey<String>('landscape-right-dpad')),
        findsOneWidget);

    await tester
        .tap(find.byKey(const ValueKey<String>('landscape-expand-toggle')));
    await tester.pump();

    expect(find.byKey(const ValueKey<String>('landscape-left-dpad')),
        findsNothing);
    expect(find.byKey(const ValueKey<String>('landscape-logo-button')),
        findsNothing);

    await tester
        .tap(find.byKey(const ValueKey<String>('landscape-expand-toggle')));
    await tester.pump();

    expect(find.byKey(const ValueKey<String>('landscape-left-dpad')),
        findsOneWidget);
    expect(find.byKey(const ValueKey<String>('landscape-logo-button')),
        findsOneWidget);
  });

  testWidgets('landscape menu matches the 844x390 Figma frame',
      (WidgetTester tester) async {
    await pumpLandscape(tester, initialMenuOpen: true);

    expect(find.byType(MenuOverlay), findsOneWidget);
    expect(find.byType(MenuCard), findsNWidgets(8));
    expect(find.byType(FocusRing), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('landscape-key-output')),
        findsNothing);

    await expectLater(
      find.byType(GamepadLandscapePage),
      matchesGoldenFile('landscape_menu.png'),
    );
  });

  testWidgets('all landscape menu actions are reachable and activatable',
      (WidgetTester tester) async {
    MenuAction? selected;
    await pumpLandscape(
      tester,
      initialMenuOpen: true,
      onMenuSelected: (MenuAction action) => selected = action,
    );

    MenuAction focusedAction() => tester
        .widgetList<MenuCard>(find.byType(MenuCard))
        .singleWhere((MenuCard card) => card.focused)
        .item
        .action;

    Future<void> moveAndActivate(
      LogicalKeyboardKey key,
      MenuAction expected,
    ) async {
      await tester.sendKeyEvent(key);
      await tester.pump();
      expect(focusedAction(), expected);
      selected = null;
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected, expected);
      if (expected == MenuAction.switchLayout) {
        expect(find.byType(LayoutSwitchOverlay), findsOneWidget);
        await tester.tap(find.text('切换布局'));
        await tester.pump();
        expect(find.byType(MenuOverlay), findsOneWidget);
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
        await tester.pump();
        expect(focusedAction(), MenuAction.switchLayout);
      } else if (expected != MenuAction.continueGame) {
        expect(find.byType(MenuOverlay), findsOneWidget);
      }
    }

    expect(focusedAction(), MenuAction.continueGame);
    await moveAndActivate(
      LogicalKeyboardKey.arrowRight,
      MenuAction.switchLayout,
    );
    await moveAndActivate(
      LogicalKeyboardKey.arrowUp,
      MenuAction.keyPosition,
    );
    await moveAndActivate(
      LogicalKeyboardKey.arrowUp,
      MenuAction.saveManagement,
    );
    await moveAndActivate(
      LogicalKeyboardKey.arrowLeft,
      MenuAction.quickLoad,
    );
    await moveAndActivate(LogicalKeyboardKey.arrowDown, MenuAction.speed);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(focusedAction(), MenuAction.keyPosition);
    await moveAndActivate(LogicalKeyboardKey.arrowRight, MenuAction.quitGame);
    await moveAndActivate(LogicalKeyboardKey.arrowUp, MenuAction.quickSave);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();
    expect(focusedAction(), MenuAction.quickLoad);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump();
    expect(focusedAction(), MenuAction.speed);
    await moveAndActivate(
      LogicalKeyboardKey.arrowDown,
      MenuAction.continueGame,
    );

    expect(find.byType(MenuOverlay), findsNothing);
  });

  testWidgets('landscape logo stays above the mask and closes the menu',
      (WidgetTester tester) async {
    await pumpLandscape(tester);
    final Finder logo =
        find.byKey(const ValueKey<String>('landscape-logo-button'));

    await tester.tap(logo);
    await tester.pump();
    expect(find.byType(MenuOverlay), findsOneWidget);

    await tester.tap(logo);
    await tester.pump();
    expect(find.byType(MenuOverlay), findsNothing);
  });

  testWidgets('switch layout menu action opens the Figma secondary overlay',
      (WidgetTester tester) async {
    await pumpLandscape(tester, initialMenuOpen: true);

    await tester.tap(
      find.byKey(const ValueKey<MenuAction>(MenuAction.switchLayout)),
    );
    await tester.pump();

    expect(find.byType(MenuOverlay), findsNothing);
    expect(find.byType(LayoutSwitchOverlay), findsOneWidget);
    expect(find.byType(LayoutChoiceCard), findsNWidgets(4));
    expect(
      tester
          .widget<LayoutChoiceCard>(
            find.byKey(
              const ValueKey<GamepadLayout>(GamepadLayout.siliconePad),
            ),
          )
          .selected,
      isTrue,
    );
  });

  testWidgets('landscape layout switch matches the 844x390 Figma frame',
      (WidgetTester tester) async {
    await pumpLandscape(tester, initialLayoutOpen: true);

    expect(find.byType(LayoutSwitchOverlay), findsOneWidget);
    expect(find.byType(LayoutChoiceCard), findsNWidgets(4));
    expect(find.byType(FocusRing), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('landscape-key-output')),
        findsNothing);

    await expectLater(
      find.byType(GamepadLandscapePage),
      matchesGoldenFile('landscape_layout_switch.png'),
    );
  });

  testWidgets('layout cards separate directional focus from selected state',
      (WidgetTester tester) async {
    GamepadLayout? selected;
    await pumpLandscape(
      tester,
      initialLayoutOpen: true,
      onLayoutSelected: (GamepadLayout layout) => selected = layout,
    );

    Finder card(GamepadLayout layout) => find.byKey(
          ValueKey<GamepadLayout>(layout),
        );
    bool isFocused(GamepadLayout layout) => find
        .descendant(of: card(layout), matching: find.byType(FocusRing))
        .evaluate()
        .isNotEmpty;
    bool isSelected(GamepadLayout layout) =>
        tester.widget<LayoutChoiceCard>(card(layout)).selected;

    expect(isFocused(GamepadLayout.retroClassic), isTrue);
    expect(isSelected(GamepadLayout.siliconePad), isTrue);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(isFocused(GamepadLayout.siliconePad), isTrue);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump();
    expect(isFocused(GamepadLayout.modernAsymmetric), isTrue);

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(selected, GamepadLayout.modernAsymmetric);
    expect(isSelected(GamepadLayout.modernAsymmetric), isTrue);
    expect(isSelected(GamepadLayout.siliconePad), isFalse);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();
    expect(isFocused(GamepadLayout.modernSymmetric), isTrue);

    await tester.tap(card(GamepadLayout.retroClassic));
    await tester.pump();
    expect(selected, GamepadLayout.retroClassic);
    expect(isSelected(GamepadLayout.retroClassic), isTrue);
  });

  testWidgets('layout back returns to menu and logo dismisses all overlays',
      (WidgetTester tester) async {
    await pumpLandscape(tester, initialLayoutOpen: true);

    await tester.tap(find.text('切换布局'));
    await tester.pump();
    expect(find.byType(LayoutSwitchOverlay), findsNothing);
    expect(find.byType(MenuOverlay), findsOneWidget);

    await tester
        .tap(find.byKey(const ValueKey<String>('landscape-logo-button')));
    await tester.pump();
    expect(find.byType(MenuOverlay), findsNothing);
    expect(find.byType(LayoutSwitchOverlay), findsNothing);
  });

  testWidgets('all landscape operation slots emit configured gamepad keys',
      (WidgetTester tester) async {
    final List<GamepadKey> pressed = <GamepadKey>[];
    await pumpLandscape(
      tester,
      onKey: pressed.add,
      showKeyLog: true,
    );

    expect(find.text('(点击任意按键测试)'), findsOneWidget);

    const List<(Offset, GamepadKey)> slots = <(Offset, GamepadKey)>[
      // 左上 DPad：上、右、下、左。
      (Offset(131.25, 72), GamepadKey.up),
      (Offset(169.5, 110.25), GamepadKey.right),
      (Offset(131.25, 148.5), GamepadKey.down),
      (Offset(93, 110.25), GamepadKey.left),
      // 左下圆形动作盘：可见上/左/右/下映射 A/B/X/Y。
      (Offset(129, 241.5), GamepadKey.a),
      (Offset(88.5, 282), GamepadKey.b),
      (Offset(169.5, 282), GamepadKey.x),
      (Offset(129, 322.5), GamepadKey.y),
      // 右上 ABXY：Y/X/B/A。
      (Offset(715, 67.5), GamepadKey.y),
      (Offset(674.5, 108), GamepadKey.x),
      (Offset(755.5, 108), GamepadKey.b),
      (Offset(715, 148.5), GamepadKey.a),
      // 右下 DPad：上、右、下、左。
      (Offset(717.25, 246), GamepadKey.up),
      (Offset(755.5, 284.25), GamepadKey.right),
      (Offset(717.25, 322.5), GamepadKey.down),
      (Offset(679, 284.25), GamepadKey.left),
      // SE / L1 / R1 / ST / L2 / R2。
      (Offset(81, 195), GamepadKey.select),
      (Offset(177, 195), GamepadKey.l1),
      (Offset(667, 195), GamepadKey.r1),
      (Offset(763, 195), GamepadKey.start),
      (Offset(324, 67), GamepadKey.l2),
      (Offset(520, 67), GamepadKey.r2),
    ];

    for (final (Offset point, GamepadKey expected) in slots) {
      await tester.tapAt(point);
      await tester.pump();
      expect(pressed.last, expected, reason: 'slot $point');
      expect(
          find.textContaining('GamepadKey.${expected.name}'), findsOneWidget);
    }

    final int beforeExpand = pressed.length;
    await tester.tapAt(const Offset(520, 357));
    await tester.pump();
    expect(pressed.length, beforeExpand, reason: '展开键是 UI 控制，不上报游戏键');
    await tester.tapAt(const Offset(520, 357));
    await tester.pump();

    await tester
        .tap(find.byKey(const ValueKey<String>('landscape-logo-button')));
    await tester.pump();

    expect(pressed.last, GamepadKey.se);
  });
}
