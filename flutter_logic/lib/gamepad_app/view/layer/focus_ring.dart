import 'package:flutter/material.dart';

/// 焦点环 —— 严格对照 Figma 3467:32888（hover遮罩）。
///
/// 结构（两层分离，不是 decoration 合一）：
/// 1. border 层：#9272f2 2px rounded12，**透明背景**
/// 2. 独立渐变光带层：斜向白色高光（256°，0→0.3→0），clip rounded12
///
/// Figma 原结构：hover遮罩(border-2 #9272f2 rounded12 透明) + 内 absolute 渐变 div。
class FocusRing extends StatelessWidget {
  const FocusRing({super.key, this.borderRadius = 12});
  final double borderRadius;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Stack(
        children: <Widget>[
          // Figma 的高光层位于 wrapper 左侧（右边缘停在 -2px），并被裁切。
          // 保留原层结构和 256° 渐变，但不把它错误铺满整张卡片。
          Positioned.fill(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(borderRadius),
              child: LayoutBuilder(
                builder: (BuildContext context, BoxConstraints constraints) {
                  return Stack(
                    clipBehavior: Clip.hardEdge,
                    children: <Widget>[
                      Positioned(
                        left: -constraints.maxWidth - 6,
                        right: constraints.maxWidth + 2,
                        top: -2,
                        bottom: -2,
                        child: const DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment(-0.97, 0.24),
                              end: Alignment(0.97, -0.24),
                              colors: <Color>[
                                Color(0x00FFFFFF),
                                Color(0x4DFFFFFF),
                                Color(0x00FFFFFF),
                              ],
                              stops: <double>[0.045073, 0.5, 0.954927],
                            ),
                          ),
                        ),
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
          // border 单独置顶：#9272F2 / 2px / rounded 12。
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: Colors.transparent,
                borderRadius: BorderRadius.circular(borderRadius),
                border: Border.all(color: const Color(0xFF9272F2), width: 2),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
