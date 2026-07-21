import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../domain/models.dart';

/// The round four-arrow pad assembled from exact Figma vector exports.
///
/// Each button remains data-driven so the artwork stays pixel exact while its
/// visible direction can report the action assigned by the Figma instance.
class TriangleDiamondPad extends StatelessWidget {
  const TriangleDiamondPad({
    super.key,
    required this.up,
    required this.down,
    required this.left,
    required this.right,
    required this.onPress,
    this.size = 126,
  });

  final GamepadKey up;
  final GamepadKey down;
  final GamepadKey left;
  final GamepadKey right;
  final ValueChanged<GamepadKey> onPress;
  final double size;

  @override
  Widget build(BuildContext context) {
    final double scale = size / 126;
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        children: <Widget>[
          _button(
            up,
            40.5,
            0,
            scale,
            angle: 0,
            circleAsset: 'assets/gamepad_app/triangle_circle_vertical.svg',
          ),
          _button(
            left,
            0,
            40.5,
            scale,
            angle: -math.pi / 2,
            circleAsset: 'assets/gamepad_app/triangle_circle_left.svg',
          ),
          _button(
            right,
            81,
            40.5,
            scale,
            angle: math.pi / 2,
            circleAsset: 'assets/gamepad_app/triangle_circle_right.svg',
          ),
          _button(
            down,
            40.5,
            81,
            scale,
            angle: math.pi,
            circleAsset: 'assets/gamepad_app/triangle_circle_vertical.svg',
          ),
        ],
      ),
    );
  }

  Widget _button(
    GamepadKey key,
    double left,
    double top,
    double scale, {
    required double angle,
    required String circleAsset,
  }) {
    return Positioned(
      left: left * scale,
      top: top * scale,
      width: 45 * scale,
      height: 45 * scale,
      child: Semantics(
        button: true,
        label: key.name,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onPress(key),
          child: Stack(
            children: <Widget>[
              Positioned(
                left: 3.6 * scale,
                top: 3.6 * scale,
                width: 37.8 * scale,
                height: 37.8 * scale,
                child: SvgPicture.asset(circleAsset, fit: BoxFit.fill),
              ),
              Center(
                child: Transform.rotate(
                  angle: angle,
                  child: SvgPicture.asset(
                    'assets/gamepad_app/triangle_arrow.svg',
                    width: 15.5885 * scale,
                    height: 9.00026 * scale,
                    fit: BoxFit.fill,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
