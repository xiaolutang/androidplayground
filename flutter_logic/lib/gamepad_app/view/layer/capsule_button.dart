import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../../domain/models.dart';

/// 胶囊按钮（select / start / L / R 等椭圆/胶囊键）。
///
/// 遵循按键三分离：UI（svgAsset/icon/label）+ 触发（key）都由 [PadKey] 注入。
/// 尺寸、描边、字号可配置，覆盖同一款胶囊的不同规格：
/// - select/start：48×21，border 1.5，字号 12
/// - L/R：72×31.5，border 2.25，字号 18（1.5×）
///
/// 底色取自 Figma：#6A7691@60% 填充、#774FEF@60% 描边、Alibaba PuHuiTi Heavy 文字。
class CapsuleButton extends StatelessWidget {
  const CapsuleButton({
    super.key,
    required this.data,
    required this.onPress,
    this.width = 48,
    this.height = 21,
    this.borderWidth = 1.5,
    this.fontSize = 12,
  });

  final PadKey data;
  final ValueChanged<GamepadKey> onPress;
  final double width;
  final double height;
  final double borderWidth;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => onPress(data.key),
      child: Container(
        width: width,
        height: height,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: const Color(0x996A7691), // #6A7691 @60%
          borderRadius: BorderRadius.circular(height / 2), // 胶囊
          border: Border.all(
              color: const Color(0x99774FEF), width: borderWidth), // #774FEF @60%
        ),
        child: _content,
      ),
    );
  }

  /// UI 由数据驱动：svgAsset → 矢量图，icon → 位图，否则 → label 文字。
  Widget get _content {
    if (data.svgAsset != null) {
      return SvgPicture.asset(data.svgAsset!, height: fontSize, fit: BoxFit.contain);
    }
    if (data.icon != null) {
      return Image(image: data.icon!, height: fontSize, fit: BoxFit.contain);
    }
    return Text(
      data.label ?? '',
      style: TextStyle(
        color: const Color(0xFFF1EDFD),
        fontSize: fontSize,
        fontWeight: FontWeight.w900, // Heavy
        fontFamily: 'AlibabaPuHuiTi',
        height: 1.0,
      ),
    );
  }
}
