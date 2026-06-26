import 'package:flutter/material.dart';
import '../focus/smart_focus_policy.dart';
import '../focus/focusable_button.dart';
import '../debug/focus_debug_overlay.dart';

/// 个人中心 Demo 页面（R002-FB005）
///
/// 验证三个焦点场景：
/// - 场景 A：首次进入右侧内容区，焦点落在 [NumericFocusOrder(1.0)] 的"会员签到"
/// - 场景 B：跨区域来回切换，焦点回到上次位置（记忆层）
/// - 场景 C：动态删除当前焦点节点，按方向键焦点不丢失（兜底层）
///
/// 布局：左导航（OrderedTraversalPolicy）+ 右内容区（SmartFocusTraversalPolicy）。
///
/// **关键**：每个 [FocusTraversalGroup] 都配对了独立的 [FocusScope]，
/// 这是 FF003 [SmartFocusTraversalPolicy] 记忆层正常工作的前提——
/// [FocusScopeNode.focusedChild] 由 [FocusScope] 维护。
///
/// **FB007 测试入口**：通过 [onDeleteCurrentFocus] public 方法暴露删除逻辑，
/// 集成测试可用 `pageKey.currentState!.onDeleteCurrentFocus()` 注入删除动作。
class PersonalCenterDemoPage extends StatefulWidget {
  /// GlobalKey，供 FB007 集成测试通过 currentState 调用 public 方法。
  /// 用法：`final pageKey = GlobalKey<PersonalCenterDemoPageState>();`
  final GlobalKey<PersonalCenterDemoPageState>? pageKey;

  const PersonalCenterDemoPage({this.pageKey, super.key});

  @override
  State<PersonalCenterDemoPage> createState() => PersonalCenterDemoPageState();
}

class PersonalCenterDemoPageState extends State<PersonalCenterDemoPage> {
  /// 右内容区按钮数据（场景 C 需要动态删除，故用 setState 管理）。
  List<_ButtonItem> _rightButtons = const <_ButtonItem>[
    _ButtonItem(label: '会员签到', order: NumericFocusOrder(1.0)),
    _ButtonItem(label: '账户信息', order: NumericFocusOrder(2.0)),
    _ButtonItem(label: '退出登录', order: null),
  ];

  /// 当前 primaryFocus 的 debugLabel，驱动调试浮层显示。
  String _primaryFocusLabel = 'null';

  /// 右侧内容区的 SmartFocusTraversalPolicy 实例引用。
  /// onResetMemory 回调通过此引用调用 [SmartFocusTraversalPolicy.resetMemory]。
  final SmartFocusTraversalPolicy _rightPolicy = SmartFocusTraversalPolicy();

  /// 右侧 FocusScope 的 GlobalKey，用于获取 [FocusScopeNode]。
  final GlobalKey _rightScopeKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    FocusManager.instance.addListener(_onFocusChange);
  }

  @override
  void dispose() {
    FocusManager.instance.removeListener(_onFocusChange);
    super.dispose();
  }

  void _onFocusChange() {
    if (!mounted) return;
    setState(() {
      _primaryFocusLabel =
          FocusManager.instance.primaryFocus?.debugLabel ?? 'null';
    });
  }

  /// **删除当前持有焦点的按钮**（场景 C 注入入口）。
  ///
  /// 逻辑：
  /// 1. 读取当前 primaryFocus 的 debugLabel。
  /// 2. 若该 label 匹配 [_rightButtons] 中某项，则 setState 移除。
  /// 3. 用 [WidgetsBinding.instance.addPostFrameCallback] 确保节点 dispose
  ///    在下一帧完成后才返回，保证后续方向键操作时焦点树已稳定。
  ///
  /// **FB007 测试入口**：此方法为 public，集成测试通过
  /// `pageKey.currentState!.onDeleteCurrentFocus()` 调用。
  @visibleForTesting
  void onDeleteCurrentFocus() {
    final String? current = FocusManager.instance.primaryFocus?.debugLabel;
    if (current == null) return;

    final bool removed = _rightButtons.any((item) => item.label == current);
    if (!removed) return;

    setState(() {
      _rightButtons =
          _rightButtons.where((item) => item.label != current).toList();
    });

    // 确保 setState 完成的下一帧，FocusNode dispose 已生效。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // 触发一次 setState 刷新调试浮层的 primaryFocusLabel
      setState(() {
        _primaryFocusLabel =
            FocusManager.instance.primaryFocus?.debugLabel ?? 'null';
      });
    });
  }

  /// 重置右侧 scope 的焦点记忆（调试浮层"重置记忆"回调）。
  void _onResetMemory() {
    final BuildContext? ctx = _rightScopeKey.currentContext;
    if (ctx == null) return;
    _rightPolicy.resetMemory(FocusScope.of(ctx));
  }

  /// 打印右侧 scope 的 rect（调试浮层"打印 Rect"回调）。
  void _onPrintRect() {
    final BuildContext? ctx = _rightScopeKey.currentContext;
    if (ctx == null) return;
    debugPrint('[FocusDebug] 右侧 scope.rect = ${FocusScope.of(ctx).rect}');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('个人中心')),
      body: Stack(
        children: [
          Row(
            children: [
              // ── 左导航（窄列）──
              // policy: OrderedTraversalPolicy（默认 Tab 顺序，不参与跨区域智能降级）
              // 配对 FocusScope：让左导航拥有独立的 focusedChild 记忆。
              Expanded(
                flex: 1,
                child: FocusScope(
                  child: FocusTraversalGroup(
                    policy: OrderedTraversalPolicy(),
                    child: Container(
                      color: Colors.grey.withValues(alpha: 0.05),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 24),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: const <Widget>[
                          FocusableButton(label: '个人中心'),
                          SizedBox(height: 12),
                          FocusableButton(label: '设置'),
                          SizedBox(height: 12),
                          FocusableButton(label: '关于'),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              // ── 右内容区（宽列）──
              // policy: SmartFocusTraversalPolicy（三层降级核心）
              // 配对 FocusScope：SmartFocusTraversalPolicy 的记忆层依赖
              // FocusScopeNode.focusedChild，必须有独立 FocusScope 才能工作。
              Expanded(
                flex: 2,
                child: FocusScope(
                  key: _rightScopeKey,
                  child: FocusTraversalGroup(
                    policy: _rightPolicy,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 32, vertical: 24),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: _rightButtons
                            .map((item) => Padding(
                                  padding:
                                      const EdgeInsets.only(bottom: 12),
                                  child: FocusableButton(
                                    label: item.label,
                                    order: item.order,
                                  ),
                                ))
                            .toList(),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
          // ── 调试浮层（D7：底部叠加，不抢焦点）──
          Positioned(
            right: 12,
            bottom: 12,
            child: FocusDebugOverlay(
              primaryFocusLabel: _primaryFocusLabel,
              onDeleteCurrentFocus: onDeleteCurrentFocus,
              onResetMemory: _onResetMemory,
              onPrintRect: _onPrintRect,
            ),
          ),
        ],
      ),
    );
  }
}

/// 右内容区按钮的数据模型。
@immutable
class _ButtonItem {
  final String label;
  final FocusOrder? order;

  const _ButtonItem({required this.label, this.order});
}
