// Pure-native vector rendering for the pantas gamepad overlay
// (Figma node 3243:13026 "55.gamepach-横屏-硅胶垫按键布局").
//
// Every shape below is redrawn from the original Figma SVG path data —
// no raster glyphs are used. Only the background illustration (bg.png) is
// a raster asset, because it is pixel-art artwork that cannot be hand-coded.

import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Minimal SVG path-string parser.
///
/// Supports the absolute commands used by the Figma-exported glyphs:
/// M (moveto, implicit lineto), L, H, V, C (cubic), Z (close). Relative
/// (lowercase) variants are handled too, for safety.
Path parseSvgPath(String d) {
  final Path path = Path();
  final List<String> tokens = _tokenize(d);
  double curX = 0, curY = 0;
  double startX = 0, startY = 0;
  String cmd = '';
  int i = 0;

  double nextNum() => double.parse(tokens[i++]);

  while (i < tokens.length) {
    final String t = tokens[i];
    if (_isAlpha(t)) {
      cmd = t;
      i++;
    }
    final bool relative = cmd.toLowerCase() == cmd;
    switch (cmd.toUpperCase()) {
      case 'M':
        curX = relative ? curX + nextNum() : nextNum();
        curY = relative ? curY + nextNum() : nextNum();
        startX = curX;
        startY = curY;
        path.moveTo(curX, curY);
        cmd = relative ? 'l' : 'L'; // subsequent pairs are implicit lineto
        break;
      case 'L':
        curX = relative ? curX + nextNum() : nextNum();
        curY = relative ? curY + nextNum() : nextNum();
        path.lineTo(curX, curY);
        break;
      case 'H':
        curX = relative ? curX + nextNum() : nextNum();
        path.lineTo(curX, curY);
        break;
      case 'V':
        curY = relative ? curY + nextNum() : nextNum();
        path.lineTo(curX, curY);
        break;
      case 'C':
        final double x1 = relative ? curX + nextNum() : nextNum();
        final double y1 = relative ? curY + nextNum() : nextNum();
        final double x2 = relative ? curX + nextNum() : nextNum();
        final double y2 = relative ? curY + nextNum() : nextNum();
        curX = relative ? curX + nextNum() : nextNum();
        curY = relative ? curY + nextNum() : nextNum();
        path.cubicTo(x1, y1, x2, y2, curX, curY);
        break;
      case 'Z':
        path.close();
        curX = startX;
        curY = startY;
        // No i++ here: the command token was already consumed above.
        break;
      default:
        i++; // unknown / stray token — skip to avoid infinite loop
        break;
    }
  }
  return path;
}

List<String> _tokenize(String d) {
  final List<String> tokens = <String>[];
  final StringBuffer buf = StringBuffer();
  void flush() {
    if (buf.isNotEmpty) {
      tokens.add(buf.toString());
      buf.clear();
    }
  }

  for (int k = 0; k < d.length; k++) {
    final String ch = d[k];
    if (_isAlpha(ch)) {
      flush();
      tokens.add(ch);
    } else if (ch == ',' ||
        ch == ' ' ||
        ch == '\t' ||
        ch == '\n' ||
        ch == '\r') {
      flush();
    } else if (ch == '-' && buf.isNotEmpty) {
      // a '-' that follows a digit starts a new number (e.g. "3-2" -> "3","-2")
      flush();
      buf.write(ch);
    } else {
      buf.write(ch);
    }
  }
  flush();
  return tokens;
}

bool _isAlpha(String ch) =>
    (ch.codeUnitAt(0) >= 65 && ch.codeUnitAt(0) <= 90) ||
    (ch.codeUnitAt(0) >= 97 && ch.codeUnitAt(0) <= 122);

// ---------------------------------------------------------------------------
// Source path data (verbatim from Figma SVG exports).
// ---------------------------------------------------------------------------

class Glyph {
  const Glyph(this.d, this.viewW, this.viewH);
  final String d;
  final double viewW;
  final double viewH;
  Path toPath() => parseSvgPath(d);
}

// ABXY letter glyphs (fill white @ 0.8).
const Glyph kLetterY = Glyph(
    'M0 0H3.77231L6.46681 5.49264H6.54972L9.24422 0H13.0165L8.2286 8.62242V14.5089H4.80865V8.66387L0 0Z',
    13.0165,
    14.5089);
const Glyph kLetterX = Glyph(
    'M7.29589 9.88676H7.21298L4.06248 14.5089H0.103635L5.16101 7.31662L0 0H3.9174L7.21298 4.74647H7.29589L10.5915 0H14.5089L9.36858 7.31662L14.426 14.5089H10.4464L7.29589 9.88676Z',
    14.5089,
    14.5089);
const Glyph kLetterB = Glyph(
    'M0 0H6.67408C8.01442 0 9.0715 0.331632 9.84531 0.994895C10.6191 1.64434 11.006 2.57705 11.006 3.79303C11.006 4.33193 10.8333 4.85702 10.4878 5.36828C10.1424 5.87955 9.67949 6.32172 9.09914 6.69481C9.94203 7.05408 10.6191 7.55843 11.1304 8.20788C11.6416 8.85732 11.8973 9.55513 11.8973 10.3013C11.8973 11.5864 11.4689 12.6089 10.6122 13.3689C9.75549 14.1289 8.60169 14.5089 7.1508 14.5089H0V0ZM6.25954 12.0009C6.95044 12.0009 7.48243 11.8075 7.85552 11.4206C8.24242 11.0198 8.43587 10.4948 8.43587 9.84531C8.43587 9.32022 8.20097 8.89187 7.73116 8.56023C7.27516 8.2286 6.58426 8.06279 5.65846 8.06279H3.41995V12.0009H6.25954ZM5.76209 6.05227C6.32863 6.05227 6.77081 5.85882 7.08862 5.47192C7.40643 5.0712 7.56534 4.63593 7.56534 4.16612C7.56534 3.6134 7.39952 3.14359 7.06789 2.75669C6.73626 2.35597 6.17663 2.1556 5.38901 2.1556H3.41995V6.05227H5.76209Z',
    11.8973,
    14.5089);
const Glyph kLetterA = Glyph(
    'M9.36859 10.4049H4.72575L3.62722 14.5089H0L4.20757 0H9.90749L14.1151 14.5089H10.4671L9.36859 10.4049ZM8.70532 7.9177L7.06789 1.8447H7.02644L5.38901 7.9177H8.70532Z',
    14.1151,
    14.5089);

// Direction triangle (fill white @ 0.8). viewBox 15.5885 x 9.00026.
const Glyph kTriangle =
    Glyph('M7.79423 0L15.5885 9.00026H0L7.79423 0Z', 15.5885, 9.00026);

// D-pad arm pad shape (rounded-top). fill #6A7691 @0.6, stroke #774FEF.
// viewBox 43.5 x 45.
const Glyph kDpadPad = Glyph(
    'M22.4824 3C28.7685 3 34.8237 3.97131 40.5 5.76953V42H3V6.25391C9.09505 4.14578 15.6525 3.00004 22.4824 3Z',
    43.5,
    45);

// D-pad arm direction arrow (white @0.8), already positioned in the 43.5x45
// base coordinate space (apex near the top, pointing outward).
const Glyph kDpadArrow =
    Glyph('M22.5 17.8453L30.2942 26.8455H14.7058L22.5 17.8453Z', 43.5, 45);

// ic_logo — circle ring + X (the "delete/close" glyph), fill #121A29. 24x24.
const Glyph kLogo = Glyph(
    'M12 4C16.4183 4 20 7.58172 20 12C20 16.4183 16.4183 20 12 20C7.58172 20 4 16.4183 4 12C4 7.58172 7.58172 4 12 4ZM15.3594 8.6416C15.0666 8.34885 14.5917 8.34898 14.2988 8.6416L12 10.9395L9.70215 8.6416C9.40925 8.34877 8.93447 8.34873 8.6416 8.6416C8.34874 8.93448 8.34877 9.40925 8.6416 9.70215L10.9395 12L8.6416 14.2988C8.34892 14.5917 8.34883 15.0665 8.6416 15.3594C8.93448 15.6517 9.40942 15.6519 9.70215 15.3594L12 13.0605L14.2988 15.3594C14.5918 15.6516 15.0667 15.652 15.3594 15.3594C15.652 15.0667 15.6516 14.5918 15.3594 14.2988L13.0605 12L15.3594 9.70215C15.6518 9.40942 15.6516 8.93446 15.3594 8.6416Z',
    24,
    24);

// Design tokens.
const Color _kPadFill = Color(0x996A7691); // #6A7691 @ 0.6
const Color _kPadStroke = Color(0x99774FEF); // #774FEF @ 0.6
const Color _kWhite80 = Color(0xCCFFFFFF); // white @ 0.8
const Color _kLogoColor = Color(0xFF121A29);
const Color _kChevronColor = Color(0xFF0A1020);

// ---------------------------------------------------------------------------
// Painters.
// ---------------------------------------------------------------------------

/// Paints a single filled glyph (letter / triangle) from its SVG path,
/// at natural 1:1 pixel scale, centered in the canvas.
class GlyphPainter extends CustomPainter {
  const GlyphPainter(this.glyph, {this.color = _kWhite80});
  final Glyph glyph;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final Rect b = glyph.toPath().getBounds();
    // Center the path's own bounding box inside the widget.
    final double dx = (size.width - b.width) / 2 - b.left;
    final double dy = (size.height - b.height) / 2 - b.top;
    canvas.translate(dx, dy);
    canvas.drawPath(
      glyph.toPath(),
      Paint()..color = color,
    );
  }

  @override
  bool shouldRepaint(covariant GlyphPainter oldDelegate) =>
      oldDelegate.glyph.d != glyph.d || oldDelegate.color != color;
}

/// The whole D-pad cross (4 arms), drawn in a 126x126 canvas at 1:1.
class DpadPainter extends CustomPainter {
  const DpadPainter();

  static const double _armW = 43.5;
  static const double _armH = 45;

  void _drawArm(Canvas canvas, double boxLeft, double boxTop, double angle) {
    canvas.save();
    canvas.translate(boxLeft + _armW / 2, boxTop + _armH / 2);
    canvas.rotate(angle);
    canvas.translate(-_armW / 2, -_armH / 2);

    final Path pad = kDpadPad.toPath();
    canvas.drawPath(pad, Paint()..color = _kPadFill);
    canvas.drawPath(
      pad,
      Paint()
        ..color = _kPadStroke
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );

    // White direction arrow, drawn at its natural position in the arm's
    // base coordinate space.
    canvas.drawPath(kDpadArrow.toPath(), Paint()..color = _kWhite80);

    canvas.restore();
  }

  @override
  void paint(Canvas canvas, Size size) {
    // Arm boxes (within the 126x126 cross) — exact Figma coordinates.
    _drawArm(canvas, 43.5, 4.5, 0); // top
    _drawArm(canvas, 81, 43.5, math.pi / 2); // right
    _drawArm(canvas, 43.5, 81, math.pi); // bottom
    _drawArm(canvas, 4.5, 43.5, -math.pi / 2); // left
  }

  @override
  bool shouldRepaint(covariant DpadPainter oldDelegate) => false;
}

/// ic_expand — a downward chevron, stroked.
class ChevronPainter extends CustomPainter {
  const ChevronPainter();
  @override
  void paint(Canvas canvas, Size size) {
    // Path "M6 9L12 15L18 9" in a 24x24 box, scaled to fit.
    final double s = size.width / 24;
    canvas.scale(s, s);
    final Paint p = Paint()
      ..color = _kChevronColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2 / s // keep visual width constant
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final Path path = Path()
      ..moveTo(6, 9)
      ..lineTo(12, 15)
      ..lineTo(18, 9);
    canvas.drawPath(path, p);
  }

  @override
  bool shouldRepaint(covariant ChevronPainter oldDelegate) => false;
}

/// ic_logo — circle ring + X, filled.
class LogoPainter extends CustomPainter {
  const LogoPainter();
  @override
  void paint(Canvas canvas, Size size) {
    final double s = size.width / 24;
    canvas.scale(s, s);
    canvas.drawPath(kLogo.toPath(), Paint()..color = _kLogoColor);
  }

  @override
  bool shouldRepaint(covariant LogoPainter oldDelegate) => false;
}
