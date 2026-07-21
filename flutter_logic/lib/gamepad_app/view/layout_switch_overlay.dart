import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../domain/models.dart';
import 'layer/focus_ring.dart';

typedef _LayoutOption = ({
  GamepadLayout layout,
  String title,
  String previewAsset,
  double unselectedPreviewOpacity,
});

/// Figma 3370:13948：横版菜单的“切换布局”二级页。
class LayoutSwitchOverlay extends StatelessWidget {
  const LayoutSwitchOverlay({
    super.key,
    required this.selectedLayout,
    required this.onSelected,
    required this.onBack,
    required this.onDismiss,
  });

  final GamepadLayout selectedLayout;
  final ValueChanged<GamepadLayout> onSelected;
  final VoidCallback onBack;
  final VoidCallback onDismiss;

  static const List<_LayoutOption> _options = <_LayoutOption>[
    (
      layout: GamepadLayout.retroClassic,
      title: '复古传统',
      previewAsset: 'assets/gamepad_app/layout_preview_retro_classic.png',
      unselectedPreviewOpacity: 1,
    ),
    (
      layout: GamepadLayout.siliconePad,
      title: '硅胶垫',
      previewAsset: 'assets/gamepad_app/layout_preview_silicone_pad.png',
      unselectedPreviewOpacity: 0.72,
    ),
    (
      layout: GamepadLayout.modernSymmetric,
      title: '现代对称',
      previewAsset: 'assets/gamepad_app/layout_preview_modern_symmetric.png',
      unselectedPreviewOpacity: 1,
    ),
    (
      layout: GamepadLayout.modernAsymmetric,
      title: '现代非对称',
      previewAsset: 'assets/gamepad_app/layout_preview_modern_asymmetric.png',
      unselectedPreviewOpacity: 1,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        const SingleActivator(LogicalKeyboardKey.escape): onBack,
      },
      child: FocusTraversalGroup(
        policy: WidgetOrderTraversalPolicy(),
        child: Stack(
          children: <Widget>[
            Positioned.fill(
              child: GestureDetector(
                key: const ValueKey<String>('layout-switch-scrim'),
                behavior: HitTestBehavior.opaque,
                onTap: onDismiss,
                child: const ColoredBox(color: Color(0xCC121A29)),
              ),
            ),
            Positioned(
              left: 246,
              top: 28,
              width: 112,
              height: 32,
              child: _BackTitle(onPressed: onBack),
            ),
            Positioned(
              left: 246,
              top: 72,
              width: 352,
              height: 238,
              child: Column(
                children: <Widget>[
                  for (int row = 0; row < 2; row++) ...<Widget>[
                    Row(
                      children: <Widget>[
                        for (int column = 0; column < 2; column++) ...<Widget>[
                          if (column > 0) const SizedBox(width: 8),
                          _choice(row * 2 + column),
                        ],
                      ],
                    ),
                    if (row == 0) const SizedBox(height: 8),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _choice(int index) {
    final _LayoutOption option = _options[index];
    return LayoutChoiceCard(
      key: ValueKey<GamepadLayout>(option.layout),
      layout: option.layout,
      title: option.title,
      previewAsset: option.previewAsset,
      unselectedPreviewOpacity: option.unselectedPreviewOpacity,
      selected: option.layout == selectedLayout,
      autofocus: index == 0,
      onPressed: () => onSelected(option.layout),
    );
  }
}

class _BackTitle extends StatelessWidget {
  const _BackTitle({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '返回菜单',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onPressed,
        child: Row(
          children: <Widget>[
            const SizedBox(width: 12),
            SizedBox(
              width: 24,
              height: 24,
              child: Center(
                child: SvgPicture.asset(
                  'assets/gamepad_app/layout_back.svg',
                  width: 8.41421,
                  height: 14,
                ),
              ),
            ),
            const SizedBox(width: 8),
            const Text(
              '切换布局',
              style: TextStyle(
                color: Color(0xFF9BA8C3),
                fontFamily: 'AlibabaPuHuiTi',
                fontSize: 14,
                fontWeight: FontWeight.w400,
                height: 18 / 14,
                letterSpacing: 0.1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 单张 172×115 布局卡；选中态和键盘焦点态相互独立。
@visibleForTesting
class LayoutChoiceCard extends StatefulWidget {
  const LayoutChoiceCard({
    super.key,
    required this.layout,
    required this.title,
    required this.previewAsset,
    required this.unselectedPreviewOpacity,
    required this.selected,
    required this.autofocus,
    required this.onPressed,
  });

  final GamepadLayout layout;
  final String title;
  final String previewAsset;
  final double unselectedPreviewOpacity;
  final bool selected;
  final bool autofocus;
  final VoidCallback onPressed;

  @override
  State<LayoutChoiceCard> createState() => _LayoutChoiceCardState();
}

class _LayoutChoiceCardState extends State<LayoutChoiceCard> {
  final FocusNode _focusNode = FocusNode();
  bool _focused = false;

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  void _activate() {
    _focusNode.requestFocus();
    widget.onPressed();
  }

  @override
  Widget build(BuildContext context) {
    return FocusableActionDetector(
      focusNode: _focusNode,
      autofocus: widget.autofocus,
      shortcuts: const <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.enter): ActivateIntent(),
        SingleActivator(LogicalKeyboardKey.space): ActivateIntent(),
      },
      actions: <Type, Action<Intent>>{
        ActivateIntent: CallbackAction<ActivateIntent>(
          onInvoke: (ActivateIntent intent) {
            _activate();
            return null;
          },
        ),
      },
      onFocusChange: (bool focused) {
        if (_focused != focused) setState(() => _focused = focused);
      },
      child: Semantics(
        button: true,
        selected: widget.selected,
        label: widget.title,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: _activate,
          child: SizedBox(
            width: 172,
            height: 115,
            child: Stack(
              children: <Widget>[
                Positioned.fill(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: widget.selected
                          ? const Color(0xFF4A3097)
                          : const Color(0xFF243147),
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),
                Positioned(
                  left: 4,
                  top: 4,
                  width: 164,
                  height: 107,
                  child: SvgPicture.asset(
                    widget.selected
                        ? 'assets/gamepad_app/layout_card_selected_bg.svg'
                        : 'assets/gamepad_app/layout_card_bg.svg',
                    fit: BoxFit.fill,
                  ),
                ),
                Positioned(
                  left: 4,
                  top: 4,
                  width: 164,
                  height: 80,
                  child: Opacity(
                    opacity:
                        widget.selected ? 1 : widget.unselectedPreviewOpacity,
                    child: Image.asset(
                      widget.previewAsset,
                      width: 164,
                      height: 80,
                      fit: BoxFit.fill,
                      filterQuality: FilterQuality.none,
                    ),
                  ),
                ),
                Positioned(
                  left: 8,
                  top: 88.5,
                  child: Text(
                    widget.title,
                    style: const TextStyle(
                      color: Color(0xFF9BA8C3),
                      fontFamily: 'AlibabaPuHuiTi',
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      height: 18 / 14,
                      letterSpacing: 0.1,
                    ),
                  ),
                ),
                Positioned(
                  left: 116,
                  top: 91,
                  width: 48,
                  height: 16,
                  child: SvgPicture.asset(
                    widget.selected
                        ? 'assets/gamepad_app/layout_toggle_on.svg'
                        : 'assets/gamepad_app/layout_toggle_off.svg',
                    fit: BoxFit.fill,
                  ),
                ),
                if (_focused)
                  const Positioned.fill(
                    child: FocusRing(borderRadius: 8),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
