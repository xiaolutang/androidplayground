import 'package:flutter/material.dart';

/// 统一封装的可聚焦按钮组件。
///
/// 内部持有 [FocusNode] 并在 [State.dispose] 时释放；
/// 根据 [FocusNode.hasFocus] 切换边框 + 缩放高亮样式；
/// 若传入 [order]，用 [FocusTraversalOrder] 包裹以支持优先级标记。
class FocusableButton extends StatefulWidget {
  /// 按钮显示文字，同时作为 [FocusNode.debugLabel]。
  final String label;

  /// 焦点遍历顺序。非 null 时用 [FocusTraversalOrder] 包裹当前按钮。
  final FocusOrder? order;

  /// 点击 / 回车键触发回调。
  final VoidCallback? onTap;

  /// 是否启用。false 时 [FocusNode.canRequestFocus] 置 false，按钮不可聚焦。
  final bool enabled;

  /// 是否自动获取焦点。true 时挂载后自动 requestFocus。
  final bool autofocus;

  const FocusableButton({
    super.key,
    required this.label,
    this.order,
    this.onTap,
    this.enabled = true,
    this.autofocus = false,
  });

  @override
  State<FocusableButton> createState() => _FocusableButtonState();
}

class _FocusableButtonState extends State<FocusableButton> {
  late final FocusNode _focusNode;

  /// 测试用：标记 dispose() 是否被调用。
  /// 通过 [isDisposed] getter 暴露给测试断言，验证 FF004 确实在 unmount 时调了 dispose。
  bool _disposed = false;

  /// @visibleForTesting：返回 [_disposed]，用于测试断言 dispose 被真正调用。
  /// 测试须在 widget unmount 前拿到 State 引用（unmount 后 tester.state() 会抛异常）。
  @visibleForTesting
  bool get isDisposed => _disposed;

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode(debugLabel: widget.label);
    _focusNode.canRequestFocus = widget.enabled;
  }

  @override
  void didUpdateWidget(covariant FocusableButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    // label 变化时更新 debugLabel，便于调试浮层辨识
    if (oldWidget.label != widget.label) {
      _focusNode.debugLabel = widget.label;
    }
    // enabled 变化时同步 canRequestFocus。
    // 放在 didUpdateWidget 而非 build()：build 应是纯函数，
    // 且每次 rebuild 无条件赋值会触发 FocusNode 内部 notifyListeners。
    if (oldWidget.enabled != widget.enabled) {
      _focusNode.canRequestFocus = widget.enabled;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // 用 Actions + ActivateIntent 处理回车 / 确认键（无障碍激活标准方式）
    Widget button = Actions(
      actions: <Type, Action<Intent>>{
        ActivateIntent: CallbackAction<ActivateIntent>(
          onInvoke: (_) => widget.enabled ? widget.onTap?.call() : null,
        ),
      },
      child: Focus(
        focusNode: _focusNode,
        autofocus: widget.autofocus,
        child: Builder(
          builder: (context) {
            final bool focused = Focus.of(context).hasFocus;
            // 注意：不使用 AnimatedScale 放大。
            // 放大后按钮会超出 SingleChildScrollView 的 clip 边界，
            // 导致焦点边框左右被裁剪（"被吃边"）。
            // 焦点高亮仅依赖边框 + 背景色 + 字重，视觉足够明显。
            //
            // margin:horizontal:2 — border 不贴 scroll viewport 边缘。
            // 原因：Border.all(width:2) 画在 rect 边界中心，外侧 1px 外延。
            // 按钮在 Column(stretch) 下撑满 scroll viewport 宽度，
            // border 外延被 SingleChildScrollView 的 Clip.hardEdge 裁掉（"吃边"）。
            // 加 2px margin 让按钮内缩，border 外延不超出 viewport。
            return AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              margin: const EdgeInsets.symmetric(horizontal: 2),
              padding:
                  const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              decoration: BoxDecoration(
                color: widget.enabled
                    ? (focused
                        ? Colors.blue.withValues(alpha: 0.12)
                        : Colors.grey.withValues(alpha: 0.06))
                    : Colors.grey.withValues(alpha: 0.04),
                borderRadius: BorderRadius.circular(8),
                border: focused
                    ? Border.all(color: Colors.blue, width: 2)
                    : Border.all(color: Colors.transparent, width: 2),
              ),
              child: InkWell(
                onTap: widget.enabled ? widget.onTap : null,
                borderRadius: BorderRadius.circular(8),
                child: Text(
                  widget.label,
                  style: TextStyle(
                    fontSize: 16,
                    color: widget.enabled
                        ? (focused ? Colors.blue : Colors.black87)
                        : Colors.black38,
                    fontWeight: focused ? FontWeight.w600 : FontWeight.normal,
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );

    // 若传入 order，用 FocusTraversalOrder 包裹以支持优先级标记
    if (widget.order != null) {
      return FocusTraversalOrder(order: widget.order!, child: button);
    }
    return button;
  }
}
