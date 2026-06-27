import 'dart:math' as math;

import 'package:flutter/material.dart';

/// 统一封装的可聚焦按钮组件。
///
/// 内部持有 [FocusNode] 并在 [State.dispose] 时释放；
/// 根据 [FocusNode.hasFocus] 切换边框 + 缩放高亮样式；
/// 若传入 [order]，用 [FocusTraversalOrder] 包裹以支持优先级标记。
///
/// R004-FB008：可选传入 [blockedNotifier] 订阅焦点边界受阻信号，
/// 当 policy 在 [inDirection] 写入受阻方向且自身是 primaryFocus 时，
/// 启动方向感知的水平/垂直抖动（±4px，250ms，3 周期 sin 波）。
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

  /// 焦点边界受阻信号通道（R004-FB008）。
  ///
  /// 非 null 时，State 内订阅此 notifier；当 policy 写入方向且自身是
  /// primaryFocus 时启动方向感知抖动。
  /// null 时行为与 R002 完全一致（向后兼容）。
  final ValueNotifier<TraversalDirection?>? blockedNotifier;

  const FocusableButton({
    super.key,
    required this.label,
    this.order,
    this.onTap,
    this.enabled = true,
    this.autofocus = false,
    this.blockedNotifier,
  });

  @override
  State<FocusableButton> createState() => _FocusableButtonState();
}

/// 抖动轴向。垂直受阻（up/down）→ dy 振荡；水平受阻（left/right）→ dx 振荡。
enum _ShakeAxis { horizontal, vertical, none }

class _FocusableButtonState extends State<FocusableButton>
    with SingleTickerProviderStateMixin {
  late final FocusNode _focusNode;

  /// 抖动动画控制器（R004-FB008）。在 initState 中创建以确保 Ticker 正确注册。
  late final AnimationController _shakeController;

  /// 当前抖动轴向（由最近一次受阻方向决定）。
  _ShakeAxis _shakeAxis = _ShakeAxis.none;

  /// notifier listener 引用（dispose 时 removeListener 用）。
  late final VoidCallback _onBlocked;

  /// 失焦 listener 引用。
  late final VoidCallback _onFocusChanged;

  /// 测试用：标记 dispose() 是否被调用。
  bool _disposed = false;

  /// @visibleForTesting：返回 [_disposed]，用于测试断言 dispose 被真正调用。
  @visibleForTesting
  bool get isDisposed => _disposed;

  /// @visibleForTesting：暴露抖动 controller（测试断言 forward/stop/dispose）。
  @visibleForTesting
  AnimationController get shakeControllerForTest => _shakeController;

  @override
  void initState() {
    super.initState();
    _focusNode = FocusNode(debugLabel: widget.label);
    _focusNode.canRequestFocus = widget.enabled;
    // 在 initState 中创建 controller，确保 Ticker 在正确的生命周期注册。
    _shakeController = AnimationController(
      duration: const Duration(milliseconds: 250),
      vsync: this,
    );
    _onBlocked = _handleBlocked;
    _onFocusChanged = _handleFocusChanged;
    widget.blockedNotifier?.addListener(_onBlocked);
    _focusNode.addListener(_onFocusChanged);
  }

  @override
  void didUpdateWidget(covariant FocusableButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    // label 变化时更新 debugLabel，便于调试浮层辨识
    if (oldWidget.label != widget.label) {
      _focusNode.debugLabel = widget.label;
    }
    // enabled 变化时同步 canRequestFocus。
    if (oldWidget.enabled != widget.enabled) {
      _focusNode.canRequestFocus = widget.enabled;
    }
    // blockedNotifier 变化时迁移监听器
    if (oldWidget.blockedNotifier != widget.blockedNotifier) {
      oldWidget.blockedNotifier?.removeListener(_onBlocked);
      widget.blockedNotifier?.addListener(_onBlocked);
    }
  }

  @override
  void dispose() {
    _disposed = true;
    widget.blockedNotifier?.removeListener(_onBlocked);
    _focusNode.removeListener(_onFocusChanged);
    _shakeController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  /// notifier listener：policy 写入受阻方向时触发。
  ///
  /// 流程：
  /// 1. 非 primaryFocus → 忽略（只有当前焦点按钮才抖）
  /// 2. 先 reset notifier.value=null（防止重入，保证单次按键只抖一次）
  /// 3. 设置抖动轴向（垂直/水平）
  /// 4. forward(from:0) — 正在动画中则重启（防抖幂等）
  void _handleBlocked() {
    final notifier = widget.blockedNotifier;
    if (notifier == null) return;
    final dir = notifier.value;
    if (dir == null) return;
    if (!_focusNode.hasFocus) return; // 非焦点不抖
    notifier.value = null; // 先 reset
    _shakeAxis = (dir == TraversalDirection.up ||
            dir == TraversalDirection.down)
        ? _ShakeAxis.vertical
        : _ShakeAxis.horizontal;
    _shakeController.forward(from: 0); // 防抖：重启而非堆叠
  }

  /// 失焦 listener：抖动中失焦 → 立即 stop，让位给正常焦点逻辑。
  void _handleFocusChanged() {
    if (!_focusNode.hasFocus && _shakeController.isAnimating) {
      _shakeController.stop();
      _shakeAxis = _ShakeAxis.none;
    }
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
            // margin:horizontal:4 — border 不贴 scroll viewport 边缘。
            // 原因：Border.all(width:2) 画在 rect 边界中心，外侧 1px 外延。
            // 按钮在 Column(stretch) 下撑满 scroll viewport 宽度，
            // border 外延被 SingleChildScrollView 的 Clip.hardEdge 裁掉（"吃边"）。
            // 加 4px margin 让按钮内缩，border 外延不超出 viewport；
            // 同时为 R004 抖动留出 ±4px 位移空间，避免水平边界按钮抖动时
            // border 被 SingleChildScrollView 的 Clip.hardEdge 裁掉。
            final container = AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              margin: const EdgeInsets.symmetric(horizontal: 4),
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

            // R004-FB008：受阻抖动包裹。
            // AnimatedBuilder 只在 _shakeController 变化时重建。
            // sin 波：t∈[0,1] → sin(3*2π*t) ∈ [-1,1]，配合 amplitude=4.0 得 ±4px。
            // idle（controller 未启动，value=0）时 sin(0)=0 → 位移=0，无 idle 偏移。
            // 动画结束（value=1）时 sin(6π)=0 → 归零，按钮回到原位。
            // ±4px 等于 margin:horizontal:4 的内缩空间，Transform.translate
            // 不会导致 border 超出 SingleChildScrollView clip 边界（R002-FIX002 教训）。
            return AnimatedBuilder(
              animation: _shakeController,
              builder: (context, child) {
                const double amplitude = 4.0;
                final double sinValue = _shakeSin(_shakeController.value);
                final double dx =
                    _shakeAxis == _ShakeAxis.horizontal
                        ? sinValue * amplitude
                        : 0.0;
                final double dy =
                    _shakeAxis == _ShakeAxis.vertical
                        ? sinValue * amplitude
                        : 0.0;
                return Transform.translate(
                  offset: Offset(dx, dy),
                  child: child,
                );
              },
              child: container,
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

/// 3 周期 sin 波形：t∈[0,1] → sin(3*2π*t) ∈ [-1, 1]。
///
/// 配合 amplitude=4.0 得到 ±4px 位移。
/// idle（controller 未启动，value=0）时 sin(0)=0 → 位移=0，无 idle 偏移。
/// 动画结束（value=1）时 sin(6π)≈0 → 归零。
///
/// 直接在 [AnimatedBuilder.builder] 中调用，不使用 [CurveTween]（后者有
/// `transform(t).round()==t` 断言，要求曲线输出∈[0,1]，sin 波违反此约束）。
double _shakeSin(double t) {
  return math.sin(3 * 2 * math.pi * t);
}
