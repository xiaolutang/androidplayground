import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'layer/menu_card.dart';
import 'layer/focus_ring.dart';

/// 横竖版共享的菜单 overlay：蒙层 + 参数化 Grid（数据驱动）。
///
/// 核心实现决策（引导 6/7）：**UI 跟数据走** —— grid 遍历 [items]，
/// 顺序/数量/焦点全由数据决定，UI（grid 容器）不动。
///
/// 默认规格对应竖版 Figma 3467:32772：342 宽 @24,75，2 列、行高 102。
/// 横版由页面注入 424 宽 @212,49，3 列、行高 65；两种规格 gap 均为 8。
/// [normalCardTrailingInset] 表达 Figma 中 Grid slot 与普通卡内容宽度的差值：
/// 横版 slot/焦点卡为 136，普通 Button 为 135，因此传 1；竖版传 0。
class MenuOverlay extends StatelessWidget {
  const MenuOverlay({
    super.key,
    required this.items,
    required this.onClose,
    required this.onSelected,
    this.panelLeft = 24,
    this.panelTop = 75,
    this.panelWidth = 342,
    this.crossAxisCount = 2,
    this.rowHeight = 102,
    this.normalCardTrailingInset = 0,
  });

  final List<MenuItem> items;
  final VoidCallback onClose;
  final ValueChanged<MenuAction> onSelected;
  final double panelLeft;
  final double panelTop;
  final double panelWidth;
  final int crossAxisCount;
  final double rowHeight;
  final double normalCardTrailingInset;

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
      Positioned(
        left: panelLeft,
        top: panelTop,
        width: panelWidth,
        child: _grid(),
      ),
    ]);
  }

  Widget _grid() {
    return GridView.builder(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      clipBehavior: Clip.none,
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossAxisCount,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
        mainAxisExtent: rowHeight,
      ),
      itemCount: items.length,
      itemBuilder: (BuildContext context, int index) {
        final MenuItem item = items[index];
        return _FocusableCell(
          key: ValueKey<MenuAction>(item.action),
          item: item,
          normalCardTrailingInset: normalCardTrailingInset,
          onPressed: () => onSelected(item.action),
        );
      },
    );
  }
}

/// 焦点单元格：Grid slot + Focus 系统 + 向外扩 4px 的 FocusRing。
///
/// FocusRing 在 wrapper 层，不在 MenuCard；wrapper 尺寸随横竖版 slot 自适应。
class _FocusableCell extends StatefulWidget {
  const _FocusableCell({
    super.key,
    required this.item,
    required this.normalCardTrailingInset,
    required this.onPressed,
  });

  final MenuItem item;
  final double normalCardTrailingInset;
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
                Positioned(
                  left: 0,
                  top: 0,
                  right: widget.normalCardTrailingInset,
                  bottom: 0,
                  child: MenuCard(item: widget.item),
                )
              else
                Positioned(
                  left: -4,
                  top: -4,
                  right: -4,
                  bottom: -4,
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
