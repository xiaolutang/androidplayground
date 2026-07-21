import 'dart:math' as math;

import 'package:flutter/material.dart';

/// The shared 844×390 game scene from Figma.
///
/// The portrait design uses the same landscape artwork rotated by 90 degrees;
/// keeping that transform here prevents the two pages from drifting apart.
class GameSceneBackground extends StatelessWidget {
  const GameSceneBackground.landscape({super.key}) : portrait = false;

  const GameSceneBackground.portrait({super.key}) : portrait = true;

  final bool portrait;

  @override
  Widget build(BuildContext context) {
    const Widget scene = SizedBox(
      width: 844,
      height: 390,
      child: Stack(
        children: <Widget>[
          Positioned(
            left: -0.253,
            top: -85,
            width: 844.4,
            height: 475,
            child: Image(
              image: AssetImage('assets/gamepad_app/bg.png'),
              fit: BoxFit.fill,
            ),
          ),
        ],
      ),
    );

    if (!portrait) {
      return const SizedBox(width: 844, height: 390, child: scene);
    }

    return SizedBox(
      width: 390,
      height: 844,
      child: ClipRect(
        child: OverflowBox(
          minWidth: 844,
          minHeight: 390,
          maxWidth: 844,
          maxHeight: 390,
          child: Transform.rotate(angle: math.pi / 2, child: scene),
        ),
      ),
    );
  }
}
