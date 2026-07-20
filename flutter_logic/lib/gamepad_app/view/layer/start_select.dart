import 'package:flutter/material.dart';
import '../../domain/models.dart';
import 'capsule_button.dart';

/// 手柄中间的 start / select 双键（垂直排列）。
///
/// [GamepadCluster] 的「中间部分」。两个胶囊键上下排列，间距取自
/// Figma 节点 3467:38417 / 3467:38420（select top 0、start top 96）。
/// 遵循按键三分离：显示与触发都由 [PadKey] 注入。
class StartSelect extends StatelessWidget {
  const StartSelect({
    super.key,
    required this.select,
    required this.start,
    required this.onPress,
  });

  final PadKey select;
  final PadKey start;
  final ValueChanged<GamepadKey> onPress;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 48,
      height: 117,
      child: Stack(children: [
        Positioned(
          left: 0,
          top: 0,
          child: CapsuleButton(data: select, onPress: onPress),
        ),
        Positioned(
          left: 0,
          top: 96,
          child: CapsuleButton(data: start, onPress: onPress),
        ),
      ]),
    );
  }
}
