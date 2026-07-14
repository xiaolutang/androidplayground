import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

const String codexUiRoute = '/codex-ui';

/// Figma node 3243:13026
/// "55.gamepach-横屏-硅胶垫按键布局".
class CodexUiDemoPage extends StatefulWidget {
  const CodexUiDemoPage({super.key});

  @override
  State<CodexUiDemoPage> createState() => _CodexUiDemoPageState();
}

class _CodexUiDemoPageState extends State<CodexUiDemoPage> {
  @override
  void initState() {
    super.initState();
    SystemChrome.setPreferredOrientations(const <DeviceOrientation>[
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(DeviceOrientation.values);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF16131B),
      body: Center(
        child: FittedBox(
          fit: BoxFit.contain,
          child: CodexUiDesignFrame(),
        ),
      ),
    );
  }
}

@visibleForTesting
class CodexUiDesignFrame extends StatelessWidget {
  const CodexUiDesignFrame({super.key});

  static const double figmaWidth = 844;
  static const double figmaHeight = 390;
  static const String backgroundAsset = 'assets/codexui/image_216.png';
  static const String deleteIconAsset = 'assets/codexui/ic_logo_delete.png';
  static const String expandIconAsset = 'assets/codexui/ic_expand.png';

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      width: figmaWidth,
      height: figmaHeight,
      child: Stack(
        clipBehavior: Clip.hardEdge,
        children: <Widget>[
          _GeneralBackground(),
          _SceneBackground(),
          _TopShoulderButton(left: 288, label: 'L2'),
          _TopShoulderButton(left: 484, label: 'R2'),
          _DpadCluster(left: 66, top: 45, rotation: -math.pi / 2),
          _FaceCluster(
              left: 66, top: 219, showLetters: false, rotation: math.pi),
          _VerticalPill(left: 70.5, top: 171, label: 'SE'),
          _VerticalPill(left: 166.5, top: 171, label: 'L1'),
          _FaceCluster(left: 652, top: 45, showLetters: true),
          _DpadCluster(
              left: 652, top: 219, rotation: -math.pi / 2, alternate: true),
          _VerticalPill(left: 656.5, top: 171, label: 'R1'),
          _VerticalPill(left: 752.5, top: 171, label: 'ST'),
          _BottomIconButton(
            left: 303,
            top: 336,
            opacity: 0.4,
            backgroundColor: Color(0xFFE7EDF8),
            asset: deleteIconAsset,
          ),
          _BottomIconButton(
            left: 499,
            top: 336,
            backgroundColor: Color(0xA6FFFFFF),
            asset: expandIconAsset,
          ),
        ],
      ),
    );
  }
}

class _GeneralBackground extends StatelessWidget {
  const _GeneralBackground();

  @override
  Widget build(BuildContext context) {
    return const Positioned.fill(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              Color(0xFFEFF3F9),
              Colors.white,
            ],
          ),
        ),
      ),
    );
  }
}

class _SceneBackground extends StatelessWidget {
  const _SceneBackground();

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: -0.2532,
      top: -84.981,
      width: 844.422,
      height: 474.981,
      child: Image.asset(
        CodexUiDesignFrame.backgroundAsset,
        fit: BoxFit.fill,
        filterQuality: FilterQuality.low,
        isAntiAlias: false,
      ),
    );
  }
}

class _BottomIconButton extends StatelessWidget {
  final double left;
  final double top;
  final Color backgroundColor;
  final double opacity;
  final String asset;

  const _BottomIconButton({
    required this.left,
    required this.top,
    required this.backgroundColor,
    required this.asset,
    this.opacity = 1,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      width: 42,
      height: 42,
      child: Opacity(
        opacity: opacity,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: backgroundColor,
            shape: BoxShape.circle,
          ),
          child: Center(
            child: Image.asset(
              asset,
              width: 24,
              height: 24,
              filterQuality: FilterQuality.low,
            ),
          ),
        ),
      ),
    );
  }
}

class _TopShoulderButton extends StatelessWidget {
  final double left;
  final String label;

  const _TopShoulderButton({
    required this.left,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: 49,
      width: 72,
      height: 36,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          Positioned(
            top: 2.25,
            width: 72,
            height: 31.5,
            child: _PillBackground(borderWidth: 2.25),
          ),
          _ButtonLabel(label: label, fontSize: 18, lineHeight: 36),
        ],
      ),
    );
  }
}

class _VerticalPill extends StatelessWidget {
  final double left;
  final double top;
  final String label;

  const _VerticalPill({
    required this.left,
    required this.top,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      width: 21,
      height: 48,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          const Positioned.fill(
            child: _PillBackground(borderWidth: 1.5),
          ),
          _ButtonLabel(label: label, fontSize: 12, lineHeight: 24),
        ],
      ),
    );
  }
}

class _PillBackground extends StatelessWidget {
  final double borderWidth;

  const _PillBackground({required this.borderWidth});

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.6,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: const Color(0xFF6A7691),
          border: Border.all(
            color: const Color(0xFF774FEF),
            width: borderWidth,
          ),
          borderRadius: BorderRadius.circular(999),
        ),
      ),
    );
  }
}

class _ButtonLabel extends StatelessWidget {
  final String label;
  final double fontSize;
  final double lineHeight;

  const _ButtonLabel({
    required this.label,
    required this.fontSize,
    required this.lineHeight,
  });

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.8,
      child: Text(
        label,
        textAlign: TextAlign.center,
        style: TextStyle(
          color: const Color(0xFFF1EDFD),
          fontSize: fontSize,
          height: lineHeight / fontSize,
          fontWeight: FontWeight.w800,
          letterSpacing: 0,
        ),
      ),
    );
  }
}

class _DpadCluster extends StatelessWidget {
  final double left;
  final double top;
  final double rotation;
  final bool alternate;

  const _DpadCluster({
    required this.left,
    required this.top,
    required this.rotation,
    this.alternate = false,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      width: 126,
      height: 126,
      child: Transform.rotate(
        angle: rotation,
        child: Stack(
          children: <Widget>[
            const _DpadPart(
              left: 43.5,
              top: 4.5,
              width: 43.5,
              height: 45,
              asset: 'assets/codexui/dpad_up.png',
            ),
            const _DpadPart(
              left: 81,
              top: 43.5,
              width: 43.5,
              height: 45,
              rotation: math.pi / 2,
              asset: 'assets/codexui/dpad_right.png',
            ),
            _DpadPart(
              left: 43.5,
              top: 81,
              width: 43.5,
              height: 45,
              flipY: true,
              asset: alternate
                  ? 'assets/codexui/dpad_down_alt.png'
                  : 'assets/codexui/dpad_up.png',
            ),
            _DpadPart(
              left: 4.5,
              top: 43.5,
              width: 43.5,
              height: 45,
              rotation: math.pi / 2,
              flipY: true,
              asset: alternate
                  ? 'assets/codexui/dpad_left_alt.png'
                  : 'assets/codexui/dpad_left.png',
            ),
          ],
        ),
      ),
    );
  }
}

class _DpadPart extends StatelessWidget {
  final double left;
  final double top;
  final double width;
  final double height;
  final double rotation;
  final bool flipY;
  final String asset;

  const _DpadPart({
    required this.left,
    required this.top,
    required this.width,
    required this.height,
    required this.asset,
    this.rotation = 0,
    this.flipY = false,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      width: width,
      height: height,
      child: Transform.rotate(
        angle: rotation,
        child: Transform.scale(
          scaleY: flipY ? -1.0 : 1.0,
          child: Image.asset(
            asset,
            fit: BoxFit.fill,
            filterQuality: FilterQuality.low,
            isAntiAlias: false,
          ),
        ),
      ),
    );
  }
}

class _FaceCluster extends StatelessWidget {
  final double left;
  final double top;
  final bool showLetters;
  final double rotation;

  const _FaceCluster({
    required this.left,
    required this.top,
    required this.showLetters,
    this.rotation = 0,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      width: 126,
      height: 126,
      child: Transform.rotate(
        angle: rotation,
        child: Stack(
          children: <Widget>[
            _FaceButton(
              left: 40.5,
              top: 0,
              circleAsset: 'assets/codexui/btn_circle_primary.png',
              symbolAsset: showLetters
                  ? 'assets/codexui/letter_y.png'
                  : 'assets/codexui/triangle_vertical.png',
              symbolWidth: showLetters ? 13.017 : 18,
              symbolHeight: showLetters ? 14.509 : 12,
            ),
            _FaceButton(
              left: 0,
              top: 40.5,
              circleAsset: 'assets/codexui/btn_circle_x.png',
              symbolAsset: showLetters
                  ? 'assets/codexui/letter_x.png'
                  : 'assets/codexui/triangle_horizontal.png',
              symbolWidth: showLetters ? 14.509 : 12,
              symbolHeight: showLetters ? 14.509 : 18,
              symbolRotation: showLetters ? 0 : math.pi / 2,
              symbolFlipY: !showLetters,
            ),
            _FaceButton(
              left: 81,
              top: 40.5,
              circleAsset: 'assets/codexui/btn_circle_secondary.png',
              symbolAsset: showLetters
                  ? 'assets/codexui/letter_b.png'
                  : 'assets/codexui/triangle_horizontal.png',
              symbolWidth: showLetters ? 11.897 : 12,
              symbolHeight: showLetters ? 14.509 : 18,
              symbolRotation: showLetters ? 0 : math.pi / 2,
            ),
            _FaceButton(
              left: 40.5,
              top: 81,
              circleAsset: 'assets/codexui/btn_circle_primary.png',
              symbolAsset: showLetters
                  ? 'assets/codexui/letter_a.png'
                  : 'assets/codexui/triangle_vertical.png',
              symbolWidth: showLetters ? 14.115 : 18,
              symbolHeight: showLetters ? 14.509 : 12,
              symbolFlipY: !showLetters,
            ),
          ],
        ),
      ),
    );
  }
}

class _FaceButton extends StatelessWidget {
  final double left;
  final double top;
  final String circleAsset;
  final String symbolAsset;
  final double symbolWidth;
  final double symbolHeight;
  final double symbolRotation;
  final bool symbolFlipY;

  const _FaceButton({
    required this.left,
    required this.top,
    required this.circleAsset,
    required this.symbolAsset,
    required this.symbolWidth,
    required this.symbolHeight,
    this.symbolRotation = 0,
    this.symbolFlipY = false,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      width: 45,
      height: 45,
      child: Stack(
        children: <Widget>[
          Positioned(
            left: 3.6,
            top: 3.6,
            width: 37.8,
            height: 37.8,
            child: Image.asset(
              circleAsset,
              fit: BoxFit.fill,
              filterQuality: FilterQuality.low,
            ),
          ),
          Center(
            child: Transform.rotate(
              angle: symbolRotation,
              child: Transform.scale(
                scaleY: symbolFlipY ? -1.0 : 1.0,
                child: Image.asset(
                  symbolAsset,
                  width: symbolWidth,
                  height: symbolHeight,
                  fit: BoxFit.fill,
                  filterQuality: FilterQuality.low,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
