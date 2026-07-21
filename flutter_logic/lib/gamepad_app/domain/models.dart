// 手柄 App 通用领域模型。
//
// 设计原则：按键标识通用化（方向只是按键的一种语义）。
// 同一个 PadKey 槽位绑 up、a、l1… 都可以，由业务决定。

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// 手柄按键标识（通用）。方向、字母、肩键、功能键统一用这一个枚举。
enum GamepadKey {
  up,
  down,
  left,
  right,
  a,
  b,
  x,
  y,
  l1,
  l2,
  r1,
  r2,
  se,
  st,
  select,
  start,
}

/// 横版虚拟手柄可切换的四种布局。
enum GamepadLayout {
  retroClassic,
  siliconePad,
  modernSymmetric,
  modernAsymmetric,
}

/// 单个按键的「显示数据」。
///
/// [key] 是这个按键"是谁"（up / a / l1… 任意）；[icon] 是它的显示资源
/// （注入，组件不写死）；[label] 是可选文字。组件只按这些数据渲染，
/// 不关心 key 的语义。
class PadKey {
  const PadKey(this.key, {this.icon, this.svgAsset, this.label});

  final GamepadKey key;
  final ImageProvider? icon; // 显示资源（PNG 等，注入）
  final String? svgAsset; // SVG 路径（flutter_svg 矢量渲染，注入）
  final String? label;

  /// 按优先级渲染按键内容：svgAsset → icon → label → 空。
  ///
  /// DPad / DiamondPad 共用此逻辑，消除两处复制粘贴的分支堆叠。
  /// [fit] 控制矢量图/位图的 fit，默认 contain。
  Widget buildContent({BoxFit fit = BoxFit.contain}) {
    if (svgAsset != null) {
      return SvgPicture.asset(svgAsset!, fit: fit);
    }
    if (icon != null) {
      return Image(image: icon!, fit: fit);
    }
    if (label != null) {
      return Center(
        child: Text(
          label!,
          style: const TextStyle(
            color: Color(0xCCFFFFFF),
            fontWeight: FontWeight.w700,
          ),
        ),
      );
    }
    return const SizedBox();
  }

  /// 命中高亮态时，叠加一层半透明紫色蒙版（DPad/DiamondPad 共用）。
  Widget buildHighlightedContent() {
    return Stack(
      fit: StackFit.expand,
      children: [
        buildContent(),
        const DecoratedBox(
          decoration: BoxDecoration(color: Color(0x99774FEF)),
        ),
      ],
    );
  }
}
