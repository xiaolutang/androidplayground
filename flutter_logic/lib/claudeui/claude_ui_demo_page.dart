// Claude UI reproduction test — pantas gamepad overlay
// (Figma node 3243:13026 "55.gamepach-横屏-硅胶垫按键布局").
//
// Everything here is rebuilt with native Flutter widgets on a fixed 844x390
// canvas (the Figma frame size). Shapes are drawn from the original vector
// path data (see gamepad_painter.dart); only the background illustration is a
// raster asset. The canvas is scaled with FittedBox to fit any screen.

import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'gamepad_painter.dart';

const String claudeUiRoute = '/claude-ui';

/// Exact Figma frame size (landscape).
const double kCanvasW = 844;
const double kCanvasH = 390;

// --- design tokens ----------------------------------------------------------
const Color _kPadFill = Color(0x996A7691); // #6A7691 @ 0.6
const Color _kPadStroke = Color(0x99774FEF); // #774FEF @ 0.6
const Color _kLabelText = Color(0xCCF1EDFD); // #F1EDFD @ 0.8
const Color _kPillFill = Color(0xFF6A7691);
const Color _kPillBorder = Color(0xFF774FEF);
const Color _kGradTop = Color(0xFFEFF3F9);
const Color _kGradBottom = Color(0xFFFFFFFF);

class ClaudeUiDemoPage extends StatefulWidget {
  const ClaudeUiDemoPage({super.key});

  @override
  State<ClaudeUiDemoPage> createState() => _ClaudeUiDemoPageState();
}

class _ClaudeUiDemoPageState extends State<ClaudeUiDemoPage> {
  @override
  void initState() {
    super.initState();
    // The source design is landscape; lock orientation + go immersive so the
    // 844x390 canvas fills the whole screen with no chrome or margins.
    SystemChrome.setPreferredOrientations(<DeviceOrientation>[
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(<DeviceOrientation>[
      DeviceOrientation.portraitUp,
    ]);
    SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.manual,
      overlays: SystemUiOverlay.values,
    );
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // No AppBar, no padding — the overlay fills the whole screen.
      extendBodyBehindAppBar: true,
      backgroundColor: const Color(0xFF16131B),
      body: Center(
        child: FittedBox(
          fit: BoxFit.contain,
          alignment: Alignment.center,
          child: SizedBox(
            width: kCanvasW,
            height: kCanvasH,
            child: const GamepadOverlay(),
          ),
        ),
      ),
    );
  }
}

/// The full 844x390 overlay, positioned with absolute Figma coordinates.
class GamepadOverlay extends StatelessWidget {
  const GamepadOverlay({super.key});

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          // 1. gradient base
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[_kGradTop, _kGradBottom],
              ),
            ),
          ),
          // 2. background illustration (clipped/offset per Figma geometry)
          _BackgroundImage(),
          // 3. shoulder triggers L2 / R2
          const Positioned(
              left: 288,
              top: 51.25,
              child: _Pill(
                  w: 72,
                  h: 31.5,
                  borderWidth: 2.25,
                  fontSize: 18,
                  label: 'L2')),
          const Positioned(
              left: 484,
              top: 51.25,
              child: _Pill(
                  w: 72,
                  h: 31.5,
                  borderWidth: 2.25,
                  fontSize: 18,
                  label: 'R2')),
          // 4. left cluster: cross (top), SE/L1 (mid), triangle diamond (bottom)
          const Positioned(left: 66, top: 45, child: _RotatedDpad()),
          const Positioned(
              left: 70.5,
              top: 171,
              child: _Pill(
                  w: 21, h: 48, borderWidth: 1.5, fontSize: 12, label: 'SE')),
          const Positioned(
              left: 166.5,
              top: 171,
              child: _Pill(
                  w: 21, h: 48, borderWidth: 1.5, fontSize: 12, label: 'L1')),
          Positioned(
            left: 66,
            top: 219,
            child: Transform.rotate(
              angle: math.pi,
              child: const _DiamondCluster(
                top: _GlyphBox(glyph: kTriangle, w: 16, h: 10),
                left: _GlyphBox(glyph: kTriangle, w: 16, h: 10),
                right: _GlyphBox(glyph: kTriangle, w: 16, h: 10),
                bottom: _GlyphBox(glyph: kTriangle, w: 16, h: 10),
              ),
            ),
          ),
          // 5. right cluster: ABXY letter diamond (top), R1/ST (mid), cross (bottom)
          const Positioned(
            left: 652,
            top: 45,
            child: _DiamondCluster(
              top: _GlyphBox(glyph: kLetterY, w: 16, h: 16),
              left: _GlyphBox(glyph: kLetterX, w: 16, h: 16),
              right: _GlyphBox(glyph: kLetterB, w: 16, h: 16),
              bottom: _GlyphBox(glyph: kLetterA, w: 16, h: 16),
            ),
          ),
          const Positioned(
              left: 656.5,
              top: 171,
              child: _Pill(
                  w: 21, h: 48, borderWidth: 1.5, fontSize: 12, label: 'R1')),
          const Positioned(
              left: 752.5,
              top: 171,
              child: _Pill(
                  w: 21, h: 48, borderWidth: 1.5, fontSize: 12, label: 'ST')),
          const Positioned(
              left: 652,
              top: 219,
              child: _RotatedDpad()),
          // 6. bottom round buttons
          const Positioned(
              left: 303, top: 336, child: _RoundIconButton(filled: false)),
          const Positioned(
              left: 499, top: 336, child: _RoundIconButton(filled: true)),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// D-pad cross, rotated -90° to mirror Figma's "test" group transform.
// ---------------------------------------------------------------------------

class _RotatedDpad extends StatelessWidget {
  const _RotatedDpad();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 126,
      height: 126,
      child: Transform.rotate(
        angle: -math.pi / 2,
        child: const CustomPaint(painter: DpadPainter()),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Background image, placed with the exact Figma clip geometry.
// ---------------------------------------------------------------------------

class _BackgroundImage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    // Figma: image is placed at left -0.03%, top -21.79%, w 100.05%, h 121.79%.
    const double leftFactor = -0.0003;
    const double topFactor = -0.2179;
    const double widthFactor = 1.0005;
    const double heightFactor = 1.2179;
    return Positioned(
      left: kCanvasW * leftFactor,
      top: kCanvasH * topFactor,
      width: kCanvasW * widthFactor,
      height: kCanvasH * heightFactor,
      child: Image.asset(
        'assets/claudeui/bg.png',
        fit: BoxFit.fill,
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Labeled pill button (L2/R2/SE/L1/R1/ST).
// ---------------------------------------------------------------------------

class _Pill extends StatelessWidget {
  const _Pill({
    required this.w,
    required this.h,
    required this.borderWidth,
    required this.fontSize,
    required this.label,
  });
  final double w;
  final double h;
  final double borderWidth;
  final double fontSize;
  final String label;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: w,
      height: h,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          // shape (fill + border) at 0.6 opacity
          Opacity(
            opacity: 0.6,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: _kPillFill,
                borderRadius:
                    BorderRadius.all(Radius.circular(math.min(w, h) / 2)),
                border: Border.all(color: _kPillBorder, width: borderWidth),
              ),
            ),
          ),
          // label at 0.8 opacity
          Center(
            child: Opacity(
              opacity: 0.8,
              child: Text(
                label,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: _kLabelText,
                  fontSize: fontSize,
                  fontFamily: 'AlibabaPuHuiTi',
                  fontWeight: FontWeight.w900,
                  height: 1.0,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Round pad (circle + centered glyph) used in the ABXY / triangle diamonds.
// ---------------------------------------------------------------------------

const double _kRoundPadSize = 37.8;

Widget _roundPad(Widget glyph) {
  return SizedBox(
    width: _kRoundPadSize,
    height: _kRoundPadSize,
    child: Stack(
      fit: StackFit.expand,
      children: <Widget>[
        DecoratedBox(
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: _kPadFill,
            border: Border.all(color: _kPadStroke, width: 1.5),
          ),
        ),
        Center(child: glyph),
      ],
    ),
  );
}

/// 126x126 diamond of four round pads. Centres (within the box):
/// top (63,22.5), left (22.5,63), right (103.5,63), bottom (63,103.5).
class _DiamondCluster extends StatelessWidget {
  const _DiamondCluster({
    required this.top,
    required this.left,
    required this.right,
    required this.bottom,
  });
  final Widget top;
  final Widget left;
  final Widget right;
  final Widget bottom;

  static const double _h = _kRoundPadSize / 2; // 18.9

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 126,
      height: 126,
      child: Stack(
        children: <Widget>[
          Positioned(left: 63 - _h, top: 22.5 - _h, child: _roundPad(top)),
          Positioned(left: 22.5 - _h, top: 63 - _h, child: _roundPad(left)),
          Positioned(left: 103.5 - _h, top: 63 - _h, child: _roundPad(right)),
          Positioned(left: 63 - _h, top: 103.5 - _h, child: _roundPad(bottom)),
        ],
      ),
    );
  }
}

/// A glyph rendered from SVG path data, centered in a w×h box.
class _GlyphBox extends StatelessWidget {
  const _GlyphBox({required this.glyph, required this.w, required this.h});
  final Glyph glyph;
  final double w;
  final double h;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: w,
      height: h,
      child: CustomPaint(painter: GlyphPainter(glyph)),
    );
  }
}

// ---------------------------------------------------------------------------
// Bottom round icon buttons (close-logo and expand-chevron).
// ---------------------------------------------------------------------------

class _RoundIconButton extends StatelessWidget {
  const _RoundIconButton({required this.filled});

  /// true → expand (chevron) on white-65 bg; false → close (logo) on light bg @0.4.
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final Widget inner = Stack(
      fit: StackFit.expand,
      children: <Widget>[
        DecoratedBox(
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: filled ? const Color(0xA6FFFFFF) : const Color(0xFFE7EDF8),
          ),
        ),
        Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CustomPaint(
                painter: filled ? const ChevronPainter() : const LogoPainter()),
          ),
        ),
      ],
    );
    // The close-logo button is rendered at 0.4 opacity as a whole.
    return SizedBox(
        width: 42,
        height: 42,
        child: filled ? inner : Opacity(opacity: 0.4, child: inner));
  }
}
