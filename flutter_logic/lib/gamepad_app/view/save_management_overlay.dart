import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../domain/models.dart';
import 'layer/focus_ring.dart';
import 'layer/save_slot_card.dart';

/// 横版「存档管理」二级 overlay（Figma 3448:30090）。
///
/// 结构（与 LayoutSwitchOverlay 同级同模式）：
/// - 全屏蒙层 0xCC121A29（点击 → onDismiss）
/// - 中央 picker-panel 443×282@(201,26) 圆角24 径向渐变背景
///   - 左上返回按钮（ic_back + 存档管理）→ onBack
///   - 快速存档区：表头(快速存档|删除) + 最近快存槽（仅 delete）
///   - 手动存档区：表头(手动存档|读取 覆盖 删除) + N 个手动槽（save/load/delete）
///   - 右侧滚动条 indicator（视觉占位）
///
/// 有状态 demo：删除真移除槽位、保存刷新时间、读取仅上报回调。
/// 焦点：CallbackShortcuts ESC=返回；首个焦点落在返回按钮。
class SaveManagementOverlay extends StatefulWidget {
  const SaveManagementOverlay({
    super.key,
    required this.onBack,
    required this.onDismiss,
  });

  final VoidCallback onBack;
  final VoidCallback onDismiss;

  @override
  State<SaveManagementOverlay> createState() => _SaveManagementOverlayState();
}

class _SaveManagementOverlayState extends State<SaveManagementOverlay> {
  SaveSlot? _quickSlot;
  late List<SaveSlot> _manualSlots;

  @override
  void initState() {
    super.initState();
    _quickSlot = const SaveSlot(
      id: 'q1',
      title: '最近快存',
      kind: SaveSlotKind.quick,
      time: '2026-07-02 14:32',
      thumbAsset: 'assets/gamepad_app/save_thumb_a.png',
    );
    _manualSlots = <SaveSlot>[
      const SaveSlot(
        id: 'm1',
        title: '存档1',
        kind: SaveSlotKind.manual,
        time: '2026-07-02 14:32',
        thumbAsset: 'assets/gamepad_app/save_thumb_a.png',
      ),
      const SaveSlot(
        id: 'm2',
        title: '存档2',
        kind: SaveSlotKind.manual,
        time: '2026-07-02 13:20',
        thumbAsset: 'assets/gamepad_app/save_thumb_b.png',
      ),
      const SaveSlot(
        id: 'm3',
        title: '存档3',
        kind: SaveSlotKind.manual,
        time: '2026-07-01 09:15',
        thumbAsset: 'assets/gamepad_app/save_thumb_a.png',
      ),
      const SaveSlot(
        id: 'm4',
        title: '存档4',
        kind: SaveSlotKind.manual,
        time: '2026-06-30 21:08',
        thumbAsset: 'assets/gamepad_app/save_thumb_b.png',
      ),
    ];
  }

  void _removeSlot(String id) {
    setState(() {
      if (_quickSlot?.id == id) {
        _quickSlot = null;
        return;
      }
      _manualSlots.removeWhere((SaveSlot s) => s.id == id);
    });
  }

  void _saveSlot(String id) {
    setState(() {
      if (_quickSlot?.id == id) {
        _quickSlot = _quickSlot!.copyWith(time: _nowLabel());
        return;
      }
      _manualSlots = _manualSlots
          .map((SaveSlot s) =>
              s.id == id ? s.copyWith(time: _nowLabel()) : s)
          .toList();
    });
  }

  void _loadSlot(String id) {
    // demo：读取仅作为可感知反馈通道，无持久化副作用。
  }

  String _nowLabel() => '刚刚';

  @override
  Widget build(BuildContext context) {
    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        const SingleActivator(LogicalKeyboardKey.escape): widget.onBack,
      },
      child: FocusTraversalGroup(
        policy: WidgetOrderTraversalPolicy(),
        child: Stack(
          children: <Widget>[
            Positioned.fill(
              child: GestureDetector(
                key: const ValueKey<String>('save_mgmt-scrim'),
                behavior: HitTestBehavior.opaque,
                onTap: widget.onDismiss,
                child: const ColoredBox(color: Color(0xCC121A29)),
              ),
            ),
            Positioned(
              key: const ValueKey<String>('save_mgmt.panel'),
              left: 201,
              top: 26,
              width: 443,
              height: 282,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(24),
                child: Stack(
                  children: <Widget>[
                    const Positioned.fill(
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: RadialGradient(
                            center: Alignment(0, -0.7),
                            radius: 1.2,
                            colors: <Color>[
                              Color(0xFFF1EDFD),
                              Color(0xFFF6FAFF),
                              Color(0xFFFFFFFF),
                            ],
                            stops: <double>[0, 0.215, 1.0],
                          ),
                        ),
                      ),
                    ),
                    Positioned(
                      key: const ValueKey<String>('save_mgmt.back_button'),
                      left: 16,
                      top: 16,
                      child: _BackTitle(onPressed: widget.onBack),
                    ),
                    Positioned(
                      key: const ValueKey<String>('save_mgmt.body'),
                      left: 16,
                      right: 16,
                      top: 56,
                      bottom: 16,
                      child: _body(),
                    ),
                    Positioned(
                      key: const ValueKey<String>('save_mgmt.scrollbar'),
                      right: 2,
                      top: 196,
                      child: Container(
                        width: 6,
                        height: 56,
                        decoration: BoxDecoration(
                          color: const Color(0xFFD4DEEF),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _body() {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          // 快速存档区
          Column(
            key: const ValueKey<String>('save_mgmt.quick_section'),
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              _SectionHeader(
                  left: '快速存档', right: const <String>['删除']),
              const SizedBox(height: 4),
              if (_quickSlot != null)
                SaveSlotCard(
                  slot: _quickSlot!,
                  onDelete: () => _removeSlot(_quickSlot!.id),
                )
              else
                _emptySlot('暂无快存'),
            ],
          ),
          const SizedBox(height: 8),
          // 手动存档区
          Column(
            key: const ValueKey<String>('save_mgmt.manual_section'),
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              _SectionHeader(
                left: '手动存档',
                right: const <String>['读取', '覆盖', '删除'],
              ),
              const SizedBox(height: 4),
              if (_manualSlots.isEmpty)
                _emptySlot('暂无存档')
              else
                for (int i = 0; i < _manualSlots.length; i++) ...<Widget>[
                  if (i > 0) const SizedBox(height: 8),
                  SaveSlotCard(
                    slot: _manualSlots[i],
                    onSave: () => _saveSlot(_manualSlots[i].id),
                    onLoad: () => _loadSlot(_manualSlots[i].id),
                    onDelete: () => _removeSlot(_manualSlots[i].id),
                  ),
                ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _emptySlot(String text) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 10),
      alignment: Alignment.center,
      child: Text(
        text,
        style: const TextStyle(
          color: Color(0xFF6A7691),
          fontSize: 12,
          fontFamily: 'AlibabaPuHuiTi',
        ),
      ),
    );
  }
}

/// 返回标题：返回箭头(#121A29) + "存档管理"（ghost 风格）。
///
/// 对照 Figma 3448:30121。可聚焦 + autofocus（overlay 打开后首个焦点）
/// + Enter/Space 激活 + FocusRing。箭头用浅色面板下的深色 ic_back.svg，
/// 文字色 #6a7691。
class _BackTitle extends StatefulWidget {
  const _BackTitle({required this.onPressed});

  final VoidCallback onPressed;

  @override
  State<_BackTitle> createState() => _BackTitleState();
}

class _BackTitleState extends State<_BackTitle> {
  final FocusNode _focusNode = FocusNode();
  bool _focused = false;

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  void _activate() => widget.onPressed();

  @override
  Widget build(BuildContext context) {
    return FocusableActionDetector(
      focusNode: _focusNode,
      autofocus: true,
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
      },
      child: Semantics(
        button: true,
        label: '返回菜单',
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: _activate,
          child: Padding(
            padding: const EdgeInsets.only(right: 4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const SizedBox(width: 12),
                SizedBox(
                  width: 24,
                  height: 24,
                  child: Stack(
                    children: <Widget>[
                      Center(
                        child: SvgPicture.asset(
                          'assets/gamepad_app/ic_back.svg',
                          width: 8.41421,
                          height: 14,
                        ),
                      ),
                      if (_focused) const FocusRing(),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                const Text(
                  '存档管理',
                  style: TextStyle(
                    color: Color(0xFF6A7691),
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
        ),
      ),
    );
  }
}

/// 分区表头：左标题 + 右操作标签列（与卡片操作按钮列右对齐）。
class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.left, required this.right});

  final String left;
  final List<String> right;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: <Widget>[
          Text(
            left,
            style: const TextStyle(
              color: Color(0xFF6A7691),
              fontSize: 14,
              fontWeight: FontWeight.w400,
              fontFamily: 'AlibabaPuHuiTi',
              height: 18 / 14,
              letterSpacing: 0.1,
            ),
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              for (int i = 0; i < right.length; i++) ...<Widget>[
                if (i > 0) const SizedBox(width: 16),
                SizedBox(
                  width: 40,
                  child: Text(
                    right[i],
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Color(0xFF6A7691),
                      fontSize: 14,
                      fontWeight: FontWeight.w400,
                      fontFamily: 'AlibabaPuHuiTi',
                      height: 18 / 14,
                      letterSpacing: 0.1,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}
