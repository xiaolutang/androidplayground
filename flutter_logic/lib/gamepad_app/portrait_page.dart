import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'domain/models.dart';
import 'view/layer/capsule_button.dart';
import 'view/layer/gamepad_cluster.dart';
import 'view/layer/start_select.dart';
import 'view/layer/diamond_pad.dart';
import 'view/layer/dpad.dart';
import 'view/layer/menu_card.dart';
import 'view/layer/round_button.dart';
import 'view/menu_overlay.dart';

const String gamepadPortraitRoute = '/gamepad-portrait';
const double _kW = 390;
const double _kH = 844;
const bool _kShowDebugBar =
    bool.fromEnvironment('showGamepadDebugBar', defaultValue: false);
const bool _kInitialMenuOpen =
    bool.fromEnvironment('gamepadMenuOpen', defaultValue: false);

const List<MenuItem> _menuItems = <MenuItem>[
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

class GamepadPortraitPage extends StatefulWidget {
  const GamepadPortraitPage({super.key});
  @override
  State<GamepadPortraitPage> createState() => _GamepadPortraitPageState();
}

class _GamepadPortraitPageState extends State<GamepadPortraitPage> {
  bool _expanded = true;
  bool _menuOpen = _kInitialMenuOpen;
  final List<String> _keyLog = [];

  void _toggle() => setState(() => _expanded = !_expanded);
  void _closeMenu() => setState(() => _menuOpen = false);
  void _toggleMenu() => setState(() => _menuOpen = !_menuOpen);

  void _onMenuSelected(MenuAction action) {
    setState(() {
      _keyLog.insert(0, action.name);
      if (_keyLog.length > 8) _keyLog.removeLast();
      if (action == MenuAction.continueGame) _menuOpen = false;
    });
  }

  /// 所有按键统一回调：记录最近 8 个 key（用于顶部调试条）。
  void _onKey(GamepadKey k) {
    setState(() {
      _keyLog.insert(0, k.name);
      if (_keyLog.length > 8) _keyLog.removeLast();
    });
  }

  @override
  void initState() {
    super.initState();
    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
        backgroundColor: const Color(0xFF16131B),
        body: Center(
            child: FittedBox(
                fit: BoxFit.contain,
                child: SizedBox(
                    width: _kW,
                    height: _kH,
                    child: _PortraitCanvas(
                      expanded: _expanded,
                      onToggle: _toggle,
                      onKey: _onKey,
                      keyLog: _keyLog,
                      menuOpen: _menuOpen,
                      onCloseMenu: _closeMenu,
                      onToggleMenu: _toggleMenu,
                      onSelectMenuItem: _onMenuSelected,
                    )))));
  }
}

class _PortraitCanvas extends StatelessWidget {
  const _PortraitCanvas({
    required this.expanded,
    required this.onToggle,
    required this.onKey,
    required this.keyLog,
    required this.menuOpen,
    required this.onCloseMenu,
    required this.onToggleMenu,
    required this.onSelectMenuItem,
  });

  final bool expanded;
  final VoidCallback onToggle;
  final ValueChanged<GamepadKey> onKey;
  final List<String> keyLog;
  final bool menuOpen;
  final VoidCallback onCloseMenu;
  final VoidCallback onToggleMenu;
  final ValueChanged<MenuAction> onSelectMenuItem;

  @override
  Widget build(BuildContext context) {
    return Stack(fit: StackFit.expand, children: [
      const _Background(),
      // 手柄核心 + L/R（收起态隐藏）
      if (expanded)
        Positioned(
          left: 45,
          top: 484,
          child: GamepadCluster(
            dpad: DPad(
              up: const PadKey(GamepadKey.up,
                  svgAsset: 'assets/gamepad_app/btn_up.svg'),
              right: const PadKey(GamepadKey.right,
                  svgAsset: 'assets/gamepad_app/btn_right.svg'),
              down: const PadKey(GamepadKey.down,
                  svgAsset: 'assets/gamepad_app/btn_down.svg'),
              left: const PadKey(GamepadKey.left,
                  svgAsset: 'assets/gamepad_app/btn_left.svg'),
              onPress: onKey,
            ),
            abxy: DiamondPad(
              // Figma：Y上 / X左 / B右 / A下
              up: const PadKey(GamepadKey.y,
                  svgAsset: 'assets/gamepad_app/btn_y.svg'),
              down: const PadKey(GamepadKey.a,
                  svgAsset: 'assets/gamepad_app/btn_a.svg'),
              left: const PadKey(GamepadKey.x,
                  svgAsset: 'assets/gamepad_app/btn_x.svg'),
              right: const PadKey(GamepadKey.b,
                  svgAsset: 'assets/gamepad_app/btn_b.svg'),
              onPress: onKey,
            ),
            middle: StartSelect(
              select: const PadKey(GamepadKey.select, label: 'select'),
              start: const PadKey(GamepadKey.start, label: 'start'),
              onPress: onKey,
            ),
            leftShoulder: CapsuleButton(
              data: const PadKey(GamepadKey.l1, label: 'L'),
              onPress: onKey,
              width: 72,
              height: 31.5,
              borderWidth: 2.25,
              fontSize: 18,
            ),
            rightShoulder: CapsuleButton(
              data: const PadKey(GamepadKey.r1, label: 'R'),
              onPress: onKey,
              width: 72,
              height: 31.5,
              borderWidth: 2.25,
              fontSize: 18,
            ),
          ),
        ),
      // 底部左：SET
      if (expanded)
        Positioned(
          left: 32,
          top: 778,
          child: RoundButton(
            data: const PadKey(GamepadKey.st,
                svgAsset: 'assets/gamepad_app/ic_dingwei.svg'),
            onPress: onKey,
          ),
        ),
      // 底部右：展开/收起开关（UI 控制，不记 keyLog）
      Positioned(
        left: 316,
        top: 778,
        child: RoundButton(
          data: PadKey(GamepadKey.l2,
              svgAsset: expanded
                  ? 'assets/gamepad_app/ic_expand.svg'
                  : 'assets/gamepad_app/ic_hide.svg'),
          onPress: (_) => onToggle(),
        ),
      ),
      // 呼出态：蒙层和面板覆盖手柄、SET、展开键；点蒙层关闭。
      if (menuOpen)
        Positioned.fill(
          child: MenuOverlay(
            onClose: onCloseMenu,
            onSelected: onSelectMenuItem,
            items: _menuItems,
          ),
        ),
      // Figma 中只有中央 logo 位于蒙层之上；菜单态为 100%，正常态为 40%。
      if (expanded)
        Positioned(
          left: 174,
          top: 778,
          child: Opacity(
            opacity: menuOpen ? 1 : 0.4,
            child: RoundButton(
              key: const ValueKey<String>('gamepad-menu-toggle'),
              data: const PadKey(
                GamepadKey.se,
                svgAsset: 'assets/gamepad_app/logo.svg',
              ),
              onPress: (_) => onToggleMenu(),
              bgColor: const Color(0xFFE7EDF8),
            ),
          ),
        ),
      // 调试信息不属于 Figma 设计，仅显式传 dart-define 时显示。
      if (_kShowDebugBar)
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          child: _DebugBar(keyLog: keyLog),
        ),
    ]);
  }
}

/// 顶部按键调试条：显示最近点击的 GamepadKey，用于确认点击数据。
class _DebugBar extends StatelessWidget {
  const _DebugBar({required this.keyLog});
  final List<String> keyLog;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Colors.black.withValues(alpha: 0.7), Colors.transparent],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Key Event →',
              style: TextStyle(
                  color: Colors.white54,
                  fontSize: 11,
                  fontFamily: 'AlibabaPuHuiTi')),
          const SizedBox(height: 4),
          Text(
            keyLog.isEmpty ? '(点击按键测试)' : keyLog.join('   '),
            style: const TextStyle(
              color: Color(0xFFB9A7FF),
              fontSize: 18,
              fontWeight: FontWeight.w900,
              fontFamily: 'AlibabaPuHuiTi',
            ),
          ),
        ],
      ),
    );
  }
}

class _Background extends StatelessWidget {
  const _Background();
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: _kW,
      height: _kH,
      child: ClipRect(
          child: OverflowBox(
              minWidth: 844,
              minHeight: 390,
              maxWidth: 844,
              maxHeight: 390,
              child: Transform.rotate(
                  angle: math.pi / 2,
                  child: SizedBox(
                      width: 844,
                      height: 390,
                      child: Stack(children: [
                        Positioned(
                            left: -0.253,
                            top: -85,
                            width: 844.4,
                            height: 475,
                            child: Image.asset('assets/gamepad_app/bg.png',
                                fit: BoxFit.fill)),
                      ]))))),
    );
  }
}
