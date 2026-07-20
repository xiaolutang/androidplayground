import 'package:flutter/material.dart';

/// 完整手柄组件：左 DPad + 右 ABXY + 中 start/select，可选 L/R 肩键。
///
/// 把各部分的相对布局封装成一个可复用的整体。坐标取自 Figma 节点
/// 3467:38414（核心）+ 3467:38407/38410（L/R）：
/// - 核心区 300×126：DPad (0,0) -90°旋转 / ABXY (174,0) / middle (126,4.5)
/// - L/R 肩键：leftShoulder (24,192) / rightShoulder (220,192)，传入则高度扩到 223.5
///
/// 三部分（+肩键）以 [Widget] 注入，组件本身只管布局。
class GamepadCluster extends StatelessWidget {
  const GamepadCluster({
    super.key,
    required this.dpad,
    required this.abxy,
    required this.middle,
    this.leftShoulder,
    this.rightShoulder,
  });

  final Widget dpad;
  final Widget abxy;
  final Widget middle;
  final Widget? leftShoulder;
  final Widget? rightShoulder;

  @override
  Widget build(BuildContext context) {
    final bool hasShoulder = leftShoulder != null || rightShoulder != null;
    return SizedBox(
      width: 300,
      height: hasShoulder ? 223.5 : 126,
      child: Stack(children: [
        // 核心区：左 DPad / 右 ABXY / 中 start-select
        Positioned(left: 0, top: 0, child: dpad),
        Positioned(left: 174, top: 0, child: abxy),
        Positioned(left: 126, top: 4.5, child: middle),
        // L/R 肩键（核心下方）
        if (leftShoulder != null)
          Positioned(left: 24, top: 192, child: leftShoulder!),
        if (rightShoulder != null)
          Positioned(left: 220, top: 192, child: rightShoulder!),
      ]),
    );
  }
}
