import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../domain/models.dart';
import 'focus_ring.dart';

/// 存档槽卡片：缩略图 + 标题 + 时间 + 操作按钮（save/load/delete）。
///
/// 对照 Figma 3448:30127（quick）/ 3448:30135（manual）：
/// - 容器 w411 bg#e7edf8 rounded8 padding8
/// - 缩略图 71×40 rounded4 + 标题 14px Heavy #121a29 + 时间 12px Regular #6a7691
/// - 操作按钮 40×40 ghost rounded4，图标按各自 viewBox 尺寸居中
///
/// [onSave]/[onLoad] 为 null 时按 quick 槽渲染（仅 delete）；非 null 按 manual 渲染。
class SaveSlotCard extends StatelessWidget {
  const SaveSlotCard({
    super.key,
    required this.slot,
    required this.onDelete,
    this.onSave,
    this.onLoad,
  });

  final SaveSlot slot;
  final VoidCallback onDelete;
  final VoidCallback? onSave;
  final VoidCallback? onLoad;

  @override
  Widget build(BuildContext context) {
    final bool isManual = slot.kind == SaveSlotKind.manual;
    return Container(
      key: ValueKey<String>('save_mgmt.slot.card.${slot.id}'),
      width: 411,
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: const Color(0xFFE7EDF8),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: <Widget>[
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: Image.asset(
              slot.thumbAsset,
              width: 71,
              height: 40,
              fit: BoxFit.cover,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  slot.title,
                  style: const TextStyle(
                    color: Color(0xFF121A29),
                    fontSize: 14,
                    fontWeight: FontWeight.w900,
                    fontFamily: 'AlibabaPuHuiTi',
                    height: 18 / 14,
                    letterSpacing: 0.1,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  slot.time,
                  style: const TextStyle(
                    color: Color(0xFF6A7691),
                    fontSize: 12,
                    fontWeight: FontWeight.w400,
                    fontFamily: 'AlibabaPuHuiTi',
                    height: 16 / 12,
                    letterSpacing: 0.2,
                  ),
                ),
              ],
            ),
          ),
          Row(
            children: <Widget>[
              if (isManual) ...<Widget>[
                _SlotIconButton(
                  key: const ValueKey<String>('save_mgmt.slot.save'),
                  iconAsset: 'assets/gamepad_app/ic_save.svg',
                  semantic: '保存',
                  iconWidth: 17.4492,
                  iconHeight: 15.8496,
                  onPressed: onSave!,
                ),
                const SizedBox(width: 16),
                _SlotIconButton(
                  key: const ValueKey<String>('save_mgmt.slot.load'),
                  iconAsset: 'assets/gamepad_app/ic_load.svg',
                  semantic: '读取',
                  iconWidth: 17.4492,
                  iconHeight: 15.8496,
                  onPressed: onLoad!,
                ),
                const SizedBox(width: 16),
              ],
              _SlotIconButton(
                key: const ValueKey<String>('save_mgmt.slot.delete'),
                iconAsset: 'assets/gamepad_app/ic_delete.svg',
                semantic: '删除',
                iconWidth: 16,
                iconHeight: 16,
                onPressed: onDelete,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// 槽位操作图标按钮：40×40 ghost，可聚焦 + Enter/Space 激活 + FocusRing。
///
/// 焦点实现对照 LayoutChoiceCard（FocusableActionDetector + FocusRing）。
/// 图标按各自 viewBox 尺寸居中（对齐 Figma 24×24 容器内的实际显示尺寸）。
class _SlotIconButton extends StatefulWidget {
  const _SlotIconButton({
    super.key,
    required this.iconAsset,
    required this.semantic,
    required this.onPressed,
    required this.iconWidth,
    required this.iconHeight,
  });

  final String iconAsset;
  final String semantic;
  final VoidCallback onPressed;
  final double iconWidth;
  final double iconHeight;

  @override
  State<_SlotIconButton> createState() => _SlotIconButtonState();
}

class _SlotIconButtonState extends State<_SlotIconButton> {
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
      shortcuts: const <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.enter): ActivateIntent(),
        SingleActivator(LogicalKeyboardKey.space): ActivateIntent(),
      },
      actions: <Type, Action<Intent>>{
        ActivateIntent: CallbackAction<ActivateIntent>(
          onInvoke: (ActivateIntent _) {
            _activate();
            return null;
          },
        ),
      },
      onFocusChange: (bool focused) {
        if (_focused != focused) setState(() => _focused = focused);
        if (focused) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Scrollable.ensureVisible(
                context,
                alignment: 0.5,
                duration: const Duration(milliseconds: 120),
              );
            }
          });
        }
      },
      child: Semantics(
        button: true,
        label: widget.semantic,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: _activate,
          child: SizedBox(
            width: 40,
            height: 40,
            child: Stack(
              children: <Widget>[
                Center(
                  child: SvgPicture.asset(
                    widget.iconAsset,
                    width: widget.iconWidth,
                    height: widget.iconHeight,
                  ),
                ),
                if (_focused) const FocusRing(borderRadius: 4),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
