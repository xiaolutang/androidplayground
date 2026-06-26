import 'package:flutter/material.dart';

/// 焦点调试浮层（FB006）
///
/// 实时显示 `primaryFocus.debugLabel`，提供三个调试动作按钮。
/// 浮层自身及内部按钮均 `canRequestFocus: false`，不干扰焦点树。
///
/// 设计决策 D7：位于底部叠加，半透明背景，不遮挡内容区焦点高亮。
///
/// 用法（由 FB005 PersonalCenterDemoPage 挂载）：
/// ```dart
/// Stack(
///   children: [
///     // ...页面内容,
///     Positioned(
///       right: 12,
///       bottom: 12,
///       child: FocusDebugOverlay(
///         primaryFocusLabel: _currentFocusLabel,
///         onDeleteCurrentFocus: _deleteCurrentFocus,
///         onResetMemory: _resetMemory,
///         onPrintRect: _printRect,
///       ),
///     ),
///   ],
/// )
/// ```
class FocusDebugOverlay extends StatelessWidget {
  /// 当前 `FocusManager.instance.primaryFocus?.debugLabel` 字符串。
  /// 由父页面通过 `setState` + `FocusManager.instance.addListener` 管理并传入。
  final String primaryFocusLabel;

  /// 删除当前持有焦点的按钮（场景 3 注入）。
  final VoidCallback onDeleteCurrentFocus;

  /// 清空右侧 scope 的记忆（反复验证场景 1）。
  final VoidCallback onResetMemory;

  /// 打印当前 scope 的 Rect（可视化区域边界）。
  final VoidCallback onPrintRect;

  const FocusDebugOverlay({
    super.key,
    required this.primaryFocusLabel,
    required this.onDeleteCurrentFocus,
    required this.onResetMemory,
    required this.onPrintRect,
  });

  @override
  Widget build(BuildContext context) {
    // 关键：整个浮层不抢焦点，避免点击浮层时干扰焦点树。
    return Focus(
      canRequestFocus: false,
      descendantsAreFocusable: false,
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: Colors.black54,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Focus: $primaryFocusLabel',
              style: const TextStyle(color: Colors.white, fontSize: 12),
            ),
            const SizedBox(height: 4),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _debugButton('删除当前焦点', onDeleteCurrentFocus),
                const SizedBox(width: 4),
                _debugButton('重置记忆', onResetMemory),
                const SizedBox(width: 4),
                _debugButton('打印 Rect', onPrintRect),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// 构建一个调试按钮。
  //
  // 不需再包 Focus(canRequestFocus: false)：外层 build() 已用
  // Focus(descendantsAreFocusable: false) 禁止整个浮层子树获取焦点。
  Widget _debugButton(String label, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: Colors.white24,
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          label,
          style: const TextStyle(color: Colors.white, fontSize: 11),
        ),
      ),
    );
  }
}
