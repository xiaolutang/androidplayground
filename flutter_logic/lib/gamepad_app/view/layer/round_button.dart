import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../../domain/models.dart';

/// 圆形按钮（底部功能键：定位/设置、logo、展开/收起开关）。
///
/// 遵循按键三分离：UI + 触发都由 [PadKey] 注入。两种渲染模式：
/// - **整图模式**：[PadKey.icon] 提供时，直接显示该图（通常是 Figma 导出的
///   按钮 PNG，已含背景+图标，最忠实，不再自画白圆）。
/// - **自绘模式**：否则画圆形背景 + 注入 [PadKey.svgAsset]/[PadKey.label]。
class RoundButton extends StatelessWidget {
  const RoundButton({
    super.key,
    required this.data,
    required this.onPress,
    this.size = 42,
    this.bgColor,
  });

  final PadKey data;
  final ValueChanged<GamepadKey> onPress;
  final double size;
  final Color? bgColor;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => onPress(data.key),
      child: data.icon != null
          // 整图模式：Figma 按钮 PNG（已含背景+图标），直接用
          ? Image(
              image: data.icon!,
              width: size,
              height: size,
              fit: BoxFit.contain,
            )
          // 自绘模式：圆形背景 + 注入矢量图标/文字
          : Container(
              width: size,
              height: size,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: bgColor ?? const Color(0xA6FFFFFF),
                shape: BoxShape.circle,
              ),
              child: _vectorContent,
            ),
    );
  }

  Widget get _vectorContent {
    if (data.svgAsset != null) {
      return SvgPicture.asset(data.svgAsset!,
          width: size, height: size, fit: BoxFit.contain);
    }
    if (data.label != null) {
      return Text(data.label!,
          style: const TextStyle(
              color: Color(0xFF0A1020),
              fontSize: 12,
              fontWeight: FontWeight.w900,
              fontFamily: 'AlibabaPuHuiTi'));
    }
    return const SizedBox();
  }
}
