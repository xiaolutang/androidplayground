import 'package:flutter/material.dart';
import '../../domain/models.dart';

class DPad extends StatelessWidget {
  const DPad({
    super.key,
    required this.up,
    required this.down,
    required this.left,
    required this.right,
    required this.onPress,
    this.highlighted = const {},
    this.opacity = 1.0,
    this.size = 126,
  });

  final PadKey up;
  final PadKey down;
  final PadKey left;
  final PadKey right;
  final ValueChanged<GamepadKey> onPress;
  final Set<GamepadKey> highlighted;
  final double opacity;
  final double size;

  @override
  Widget build(BuildContext context) {
    final double s = size / 126;
    return Opacity(
      opacity: opacity,
      child: SizedBox(
        width: size,
        height: size,
        child: Stack(children: [
          // 臂坐标取自 Figma 节点 3467:38415（126 容器内），每臂 43.5×45 ≈ ABXY 的 45×45
          _arm(up, 43.5, 4.5, 43.5, 45, s),
          _arm(right, 81, 43.5, 45, 43.5, s),
          _arm(down, 43.5, 81, 43.5, 45, s),
          _arm(left, 4.5, 43.5, 45, 43.5, s),
        ]),
      ),
    );
  }

  Widget _arm(PadKey k, double l, double t, double w, double h, double s) {
    final Widget content = highlighted.contains(k.key)
        ? k.buildHighlightedContent()
        : k.buildContent();
    return Positioned(
      left: l * s,
      top: t * s,
      width: w * s,
      height: h * s,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => onPress(k.key),
        child: content,
      ),
    );
  }
}
