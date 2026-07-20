import 'package:flutter/material.dart';
import '../../domain/models.dart';

/// 菱形四按键簇（右侧动作键：可绑 ABXY / WASD / 任意四键）。
///
/// 与 [DPad] 同构，只负责「按注入资源渲染 + 按回调触发」，
/// **不绑死任何按键语义**——四个槽位是位置（上/下/左/右），
/// 每个槽位绑哪个 [GamepadKey]、显示哪张图，完全由上层 [PadKey] 数据决定。
///
/// - 换绑定：ABXY → WASD，只改 4 个 [PadKey]，组件一行不动。
/// - 换皮肤：换 [PadKey.svgAsset]，组件一行不动。
///
/// 布局坐标取自 Figma 节点 3467:38416：菱形顶点，每格 45×45。
class DiamondPad extends StatelessWidget {
  const DiamondPad({
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
          _btn(up, 40.5, 0, s),
          _btn(left, 0, 40.5, s),
          _btn(right, 81, 40.5, s),
          _btn(down, 40.5, 81, s),
        ]),
      ),
    );
  }

  Widget _btn(PadKey k, double l, double t, double s) {
    final Widget content = highlighted.contains(k.key)
        ? k.buildHighlightedContent()
        : k.buildContent();
    return Positioned(
      left: l * s,
      top: t * s,
      width: 45 * s,
      height: 45 * s,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => onPress(k.key),
        child: content,
      ),
    );
  }
}
