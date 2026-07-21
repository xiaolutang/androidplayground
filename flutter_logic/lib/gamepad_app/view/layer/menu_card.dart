import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// 菜单行为标识。页面层决定每个行为的业务结果，卡片组件只负责上报。
enum MenuAction {
  quickSave,
  quitGame,
  saveManagement,
  speed,
  quickLoad,
  continueGame,
  keyPosition,
  switchLayout,
}

/// 菜单卡片规格：显示、行为和初始状态全部由数据描述。
class MenuItem {
  const MenuItem({
    required this.action,
    required this.title,
    required this.icon,
    this.caption,
    this.initiallyFocused = false,
    this.iconRenderSize = 24,
  });

  final MenuAction action;
  final String title;
  final String icon;
  final String? caption;
  final bool initiallyFocused;
  final double iconRenderSize;
}

/// 公共菜单卡片：icon + 双行文字（纯内容，不含 Focus 系统/FocusRing）。
///
/// Focus 系统和 FocusRing 由外层 _FocusableCell 管理（wrapper 层）。
/// MenuCard 只负责渲染内容，色由 [focused] 参数驱动。
///
/// 对照 Figma 3467:32776：Row(icon+文字 gap4 center)，bg rounded8 padding8，
/// icon 容器 34×34 p5 rounded4 内 icon24，title Heavy14 #121a29，caption Regular12 #6a7691。
class MenuCard extends StatelessWidget {
  const MenuCard({super.key, required this.item, this.focused = false});
  final MenuItem item;
  final bool focused;

  @override
  Widget build(BuildContext context) {
    final f = focused;
    return Container(
      decoration: BoxDecoration(
        color: f ? const Color(0xFFC9B9F9) : const Color(0xFFE7EDF8),
        borderRadius: BorderRadius.circular(8),
      ),
      padding: const EdgeInsets.all(8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            width: 34,
            height: 34,
            padding: const EdgeInsets.all(5),
            decoration: BoxDecoration(borderRadius: BorderRadius.circular(4)),
            child: OverflowBox(
              minWidth: item.iconRenderSize,
              maxWidth: item.iconRenderSize,
              minHeight: item.iconRenderSize,
              maxHeight: item.iconRenderSize,
              child: SvgPicture.asset(
                item.icon,
                width: item.iconRenderSize,
                height: item.iconRenderSize,
                fit: BoxFit.contain,
                colorFilter: ColorFilter.mode(
                  f ? const Color(0xFF774FEF) : const Color(0xFF333333),
                  BlendMode.srcIn,
                ),
              ),
            ),
          ),
          const SizedBox(width: 4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  item.title,
                  maxLines: 1,
                  softWrap: false,
                  overflow: TextOverflow.visible,
                  style: TextStyle(
                    color:
                        f ? const Color(0xFF774FEF) : const Color(0xFF121A29),
                    fontSize: 14,
                    fontWeight: FontWeight.w900,
                    fontFamily: 'AlibabaPuHuiTi',
                    height: 18 / 14,
                    letterSpacing: 0.1,
                  ),
                ),
                if (item.caption != null)
                  Text(
                    item.caption!,
                    maxLines: 1,
                    softWrap: false,
                    overflow: TextOverflow.visible,
                    style: TextStyle(
                      color:
                          f ? const Color(0xFF774FEF) : const Color(0xFF6A7691),
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
        ],
      ),
    );
  }
}
