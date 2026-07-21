import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'domain/models.dart';
import 'view/layer/capsule_button.dart';
import 'view/layer/diamond_pad.dart';
import 'view/layer/dpad.dart';
import 'view/layer/game_scene_background.dart';
import 'view/layer/menu_card.dart';
import 'view/layer/round_button.dart';
import 'view/layer/triangle_diamond_pad.dart';
import 'view/menu_overlay.dart';

const String gamepadLandscapeRoute = '/gamepad-landscape';
const double _canvasWidth = 844;
const double _canvasHeight = 390;
const bool _initialLandscapeMenuOpen = bool.fromEnvironment(
  'gamepadLandscapeMenuOpen',
  defaultValue: false,
);

const List<MenuItem> _landscapeMenuItems = <MenuItem>[
  MenuItem(
    action: MenuAction.quickLoad,
    title: '快速读档',
    icon: 'assets/gamepad_app/ic_save.svg',
    caption: '14:32',
    iconRenderSize: 17.4492,
  ),
  MenuItem(
    action: MenuAction.saveManagement,
    title: '存档管理',
    icon: 'assets/gamepad_app/ic_cundang.svg',
    caption: '3/3 已用',
    iconRenderSize: 15.8506,
  ),
  MenuItem(
    action: MenuAction.quickSave,
    title: '快速存档',
    icon: 'assets/gamepad_app/ic_load.svg',
    caption: '覆盖快速存档',
    iconRenderSize: 17.4492,
  ),
  MenuItem(
    action: MenuAction.speed,
    title: '倍速',
    icon: 'assets/gamepad_app/ic_beisu.svg',
    iconRenderSize: 17.45,
  ),
  MenuItem(
    action: MenuAction.keyPosition,
    title: '按键定位',
    icon: 'assets/gamepad_app/ic_dingwei.svg',
    iconRenderSize: 42,
  ),
  MenuItem(
    action: MenuAction.quitGame,
    title: '退出游戏',
    icon: 'assets/gamepad_app/ic_quit.svg',
    iconRenderSize: 15.9258,
  ),
  MenuItem(
    action: MenuAction.continueGame,
    title: '继续游戏',
    icon: 'assets/gamepad_app/ic_jixu.svg',
    caption: '返回游戏',
    initiallyFocused: true,
    iconRenderSize: 15.9951,
  ),
  MenuItem(
    action: MenuAction.switchLayout,
    title: '切换布局',
    icon: 'assets/gamepad_app/ic_layout.svg',
    iconRenderSize: 16,
  ),
];

class GamepadLandscapePage extends StatefulWidget {
  const GamepadLandscapePage({
    super.key,
    this.onKey,
    this.onMenuSelected,
    this.showKeyLog = true,
    this.initialMenuOpen = _initialLandscapeMenuOpen,
  });

  /// Connects the visual controls to an emulator/game input adapter.
  final ValueChanged<GamepadKey>? onKey;
  final ValueChanged<MenuAction>? onMenuSelected;

  /// Shows the latest key payloads on the playground page for manual testing.
  final bool showKeyLog;
  final bool initialMenuOpen;

  @override
  State<GamepadLandscapePage> createState() => _GamepadLandscapePageState();
}

class _GamepadLandscapePageState extends State<GamepadLandscapePage> {
  bool _expanded = true;
  late bool _menuOpen;
  final List<GamepadKey> _keyLog = <GamepadKey>[];

  @override
  void initState() {
    super.initState();
    _menuOpen = widget.initialMenuOpen;
    SystemChrome.setPreferredOrientations(const <DeviceOrientation>[
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.manual,
      overlays: const <SystemUiOverlay>[],
    );
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(DeviceOrientation.values);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  void _onKey(GamepadKey key) {
    if (widget.showKeyLog) setState(() => _recordKey(key));
    widget.onKey?.call(key);
  }

  void _recordKey(GamepadKey key) {
    _keyLog.insert(0, key);
    if (_keyLog.length > 8) _keyLog.removeLast();
  }

  void _toggleExpanded() => setState(() => _expanded = !_expanded);

  void _toggleMenu() {
    setState(() {
      if (widget.showKeyLog) _recordKey(GamepadKey.se);
      _menuOpen = !_menuOpen;
    });
    widget.onKey?.call(GamepadKey.se);
  }

  void _closeMenu() => setState(() => _menuOpen = false);

  void _selectMenuItem(MenuAction action) {
    widget.onMenuSelected?.call(action);
    if (action == MenuAction.continueGame) _closeMenu();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF16131B),
      body: Center(
        child: FittedBox(
          fit: BoxFit.contain,
          child: SizedBox(
            width: _canvasWidth,
            height: _canvasHeight,
            child: _LandscapeCanvas(
              expanded: _expanded,
              menuOpen: _menuOpen,
              keyLog: _keyLog,
              showKeyLog: widget.showKeyLog,
              onKey: _onKey,
              onToggleExpanded: _toggleExpanded,
              onToggleMenu: _toggleMenu,
              onCloseMenu: _closeMenu,
              onSelectMenuItem: _selectMenuItem,
            ),
          ),
        ),
      ),
    );
  }
}

class _LandscapeCanvas extends StatelessWidget {
  const _LandscapeCanvas({
    required this.expanded,
    required this.menuOpen,
    required this.keyLog,
    required this.showKeyLog,
    required this.onKey,
    required this.onToggleExpanded,
    required this.onToggleMenu,
    required this.onCloseMenu,
    required this.onSelectMenuItem,
  });

  final bool expanded;
  final bool menuOpen;
  final List<GamepadKey> keyLog;
  final bool showKeyLog;
  final ValueChanged<GamepadKey> onKey;
  final VoidCallback onToggleExpanded;
  final VoidCallback onToggleMenu;
  final VoidCallback onCloseMenu;
  final ValueChanged<MenuAction> onSelectMenuItem;

  static const PadKey _up =
      PadKey(GamepadKey.up, svgAsset: 'assets/gamepad_app/btn_up.svg');
  static const PadKey _down =
      PadKey(GamepadKey.down, svgAsset: 'assets/gamepad_app/btn_down.svg');
  static const PadKey _left =
      PadKey(GamepadKey.left, svgAsset: 'assets/gamepad_app/btn_left.svg');
  static const PadKey _right =
      PadKey(GamepadKey.right, svgAsset: 'assets/gamepad_app/btn_right.svg');
  static const PadKey _a =
      PadKey(GamepadKey.a, svgAsset: 'assets/gamepad_app/btn_a.svg');
  static const PadKey _b =
      PadKey(GamepadKey.b, svgAsset: 'assets/gamepad_app/btn_b.svg');
  static const PadKey _x =
      PadKey(GamepadKey.x, svgAsset: 'assets/gamepad_app/btn_x.svg');
  static const PadKey _y =
      PadKey(GamepadKey.y, svgAsset: 'assets/gamepad_app/btn_y.svg');

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        const GameSceneBackground.landscape(),
        if (expanded) ...<Widget>[
          Positioned(
            key: const ValueKey<String>('landscape-left-dpad'),
            left: 66,
            top: 45,
            child: DPad(
              up: _up,
              down: _down,
              left: _left,
              right: _right,
              onPress: onKey,
            ),
          ),
          Positioned(
            key: const ValueKey<String>('landscape-left-action-pad'),
            left: 66,
            top: 219,
            child: TriangleDiamondPad(
              // The exported Figma instance is rotated 180°: A/B/X/Y end up
              // at the visible top/left/right/bottom slots respectively.
              up: GamepadKey.a,
              left: GamepadKey.b,
              right: GamepadKey.x,
              down: GamepadKey.y,
              onPress: onKey,
            ),
          ),
          Positioned(
            key: const ValueKey<String>('landscape-right-action-pad'),
            left: 652,
            top: 45,
            child: DiamondPad(
              up: _y,
              down: _a,
              left: _x,
              right: _b,
              onPress: onKey,
            ),
          ),
          Positioned(
            key: const ValueKey<String>('landscape-right-dpad'),
            left: 652,
            top: 219,
            child: DPad(
              up: _up,
              down: _down,
              left: _left,
              right: _right,
              onPress: onKey,
            ),
          ),
          _capsule(70.5, 171, GamepadKey.select, 'SE', vertical: true),
          _capsule(166.5, 171, GamepadKey.l1, 'L1', vertical: true),
          _capsule(656.5, 171, GamepadKey.r1, 'R1', vertical: true),
          _capsule(752.5, 171, GamepadKey.start, 'ST', vertical: true),
          _capsule(288, 51.25, GamepadKey.l2, 'L2'),
          _capsule(484, 51.25, GamepadKey.r2, 'R2'),
        ],
        Positioned(
          left: menuOpen ? 514 : 499,
          top: 336,
          child: RoundButton(
            key: const ValueKey<String>('landscape-expand-toggle'),
            data: PadKey(
              GamepadKey.st,
              svgAsset: expanded
                  ? 'assets/gamepad_app/ic_expand.svg'
                  : 'assets/gamepad_app/ic_hide.svg',
            ),
            onPress: (_) => onToggleExpanded(),
          ),
        ),
        if (menuOpen)
          Positioned.fill(
            child: MenuOverlay(
              items: _landscapeMenuItems,
              onClose: onCloseMenu,
              onSelected: onSelectMenuItem,
              panelLeft: 212,
              panelTop: 49,
              panelWidth: 424,
              crossAxisCount: 3,
              rowHeight: 65,
              normalCardTrailingInset: 1,
            ),
          ),
        if (expanded)
          Positioned(
            left: 303,
            top: 336,
            child: Opacity(
              opacity: menuOpen ? 1 : 0.4,
              child: RoundButton(
                key: const ValueKey<String>('landscape-logo-button'),
                data: const PadKey(
                  GamepadKey.se,
                  svgAsset: 'assets/gamepad_app/logo.svg',
                ),
                onPress: (_) => onToggleMenu(),
                bgColor: const Color(0xFFE7EDF8),
              ),
            ),
          ),
        if (showKeyLog && !menuOpen)
          Positioned(
            left: 242,
            top: 144,
            width: 360,
            child: _KeyOutputPanel(keyLog: keyLog),
          ),
      ],
    );
  }

  Widget _capsule(
    double left,
    double top,
    GamepadKey key,
    String label, {
    bool vertical = false,
  }) {
    return Positioned(
      left: left,
      top: top,
      child: CapsuleButton(
        data: PadKey(key, label: label),
        onPress: onKey,
        width: vertical ? 21 : 72,
        height: vertical ? 48 : 31.5,
        borderWidth: vertical ? 1.5 : 2.25,
        fontSize: vertical ? 12 : 18,
      ),
    );
  }
}

class _KeyOutputPanel extends StatelessWidget {
  const _KeyOutputPanel({required this.keyLog});

  final List<GamepadKey> keyLog;

  @override
  Widget build(BuildContext context) {
    final String output = keyLog.isEmpty
        ? '(点击任意按键测试)'
        : keyLog
            .map((GamepadKey key) => 'GamepadKey.${key.name}')
            .join('  ·  ');

    return Container(
      key: const ValueKey<String>('landscape-key-output'),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xD9121A29),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFF9272F2)),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: Color(0x660A1020),
            blurRadius: 12,
            offset: Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Key Event →',
            style: TextStyle(
              color: Color(0xFFB9A7FF),
              fontSize: 11,
              fontFamily: 'AlibabaPuHuiTi',
              fontWeight: FontWeight.w700,
              height: 1.2,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            output,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 13,
              fontFamily: 'AlibabaPuHuiTi',
              fontWeight: FontWeight.w900,
              height: 1.3,
            ),
          ),
        ],
      ),
    );
  }
}
