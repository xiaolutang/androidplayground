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

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode(debugLabel: widget.label);
  }

  @override
  void didUpdateWidget(covariant FocusableButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    // label 变化时更新 debugLabel，便于调试浮层辨识
    // canRequestFocus 同步由 build() 负责，此处不重复
    if (oldWidget.label != widget.label) {
      _focusNode.debugLabel = widget.label;
    }
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // 同步 enabled → canRequestFocus（初始值/外部变更均覆盖）
    _focusNode.canRequestFocus = widget.enabled;

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
            return AnimatedScale(
              scale: focused ? 1.05 : 1.0,
              duration: const Duration(milliseconds: 150),
              curve: Curves.easeOut,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
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
                      fontWeight:
                          focused ? FontWeight.w600 : FontWeight.normal,
                    ),
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
