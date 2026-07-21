import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'layer/menu_card.dart';
import 'layer/focus_ring.dart';

/// 菜单 overlay：蒙层 + 面板（grid 列表，数据驱动）。
///
/// 核心实现决策（引导 6/7）：**UI 跟数据走** —— grid 遍历 [items]，
/// 顺序/数量/焦点全由数据决定，UI（grid 容器）不动。
///
/// 布局取自 Figma 3467:32772：面板 342×322 @24,75，grid 2列×3行 gap8。
/// 焦点项（继续游戏）：_FocusableCell（wrapper 175×110 padding4 rounded16 + FocusRing inset0）。
class MenuOverlay extends StatelessWidget {
  const MenuOverlay({
    super.key,
    required this.items,
    required this.onClose,
    required this.onSelected,
  });

  final List<MenuItem> items;
  final VoidCallback onClose;
  final ValueChanged<MenuAction> onSelected;

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      Positioned.fill(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onClose,
          child: const ColoredBox(
              color: Color(0xCC121A29), child: SizedBox.expand()),
        ),
      ),
      Positioned(left: 24, top: 75, width: 342, child: _grid()),
    ]);
  }

  Widget _grid() {
    return GridView.builder(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      clipBehavior: Clip.none,
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
        mainAxisExtent: 102,
      ),
      itemCount: items.length,
      itemBuilder: (BuildContext context, int index) {
        final MenuItem item = items[index];
        return _FocusableCell(
          key: ValueKey<MenuAction>(item.action),
          item: item,
          onPressed: () => onSelected(item.action),
        );
      },
    );
  }
}

/// 焦点单元格：wrapper（Figma 3467:32880 Frame 6）+ Focus 系统 + FocusRing inset0。
///
/// 结构：Transform.translate(-4) + SizedBox(175×110) + Padding(4) + Stack[MenuCard, FocusRing]。
/// FocusRing 在 wrapper 层 inset0（Figma hover遮罩 inset0），不在 MenuCard。
class _FocusableCell extends StatefulWidget {
  const _FocusableCell({
    super.key,
    required this.item,
    required this.onPressed,
  });

  final MenuItem item;
  final VoidCallback onPressed;

  @override
  State<_FocusableCell> createState() => _FocusableCellState();
}

class _FocusableCellState extends State<_FocusableCell> {
  bool _focused = false;

  void _activate() => widget.onPressed();

  @override
  Widget build(BuildContext context) {
    return FocusableActionDetector(
      autofocus: widget.item.initiallyFocused,
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
      onFocusChange: (bool value) {
        if (_focused != value) setState(() => _focused = value);
      },
      child: Semantics(
        button: true,
        label: widget.item.caption == null
            ? widget.item.title
            : '${widget.item.title}，${widget.item.caption}',
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: _activate,
          child: Stack(
            clipBehavior: Clip.none,
            children: <Widget>[
              if (!_focused)
                Positioned.fill(child: MenuCard(item: widget.item))
              else
                Positioned(
                  left: -4,
                  top: -4,
                  width: 175,
                  height: 110,
                  child: Stack(
                    children: <Widget>[
                      Padding(
                        padding: const EdgeInsets.all(4),
                        child: MenuCard(item: widget.item, focused: true),
                      ),
                      const Positioned.fill(child: FocusRing()),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
