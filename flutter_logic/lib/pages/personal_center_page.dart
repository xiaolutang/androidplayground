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
/// 布局：左导航 + 右内容区，共用一个 [FocusTraversalGroup]
/// （[SmartFocusTraversalPolicy]）。
///
/// **关键**（FB007 修复）：
/// - 整个 body 外层包一个 [FocusTraversalGroup]（[SmartFocusTraversalPolicy]），
///   子区域**不**各自创建独立 group。
///   这样 `FocusTraversalGroup.of()` 始终返回外层 SmartFocusTraversalPolicy，
///   `nearestScope.traversalDescendants` 包含所有区域的节点，
///   方向键候选搜索能跨越区域边界。
/// - 右内容区保留独立 [FocusScope]（不配 [FocusTraversalGroup]），
///   为 [SmartFocusTraversalPolicy] 记忆层提供 [FocusScopeNode.focusedChild]。
///
/// **FB007 测试入口**：通过 [onDeleteCurrentFocus] public 方法暴露删除逻辑，
/// 集成测试可用 `tester.state` 拿到 `PersonalCenterDemoPageState` 后调用
/// [onDeleteCurrentFocus] 注入删除动作。
class PersonalCenterDemoPage extends StatefulWidget {
  const PersonalCenterDemoPage({super.key});

  @override
  State<PersonalCenterDemoPage> createState() => PersonalCenterDemoPageState();
}

class PersonalCenterDemoPageState extends State<PersonalCenterDemoPage> {
  /// 右内容区按钮数据（场景 C 需要动态删除，故用 setState 管理）。
  List<_ButtonItem> _rightButtons = const <_ButtonItem>[
    _ButtonItem(label: '会员签到', order: NumericFocusOrder(1.0)),
    _ButtonItem(label: '账户信息', order: NumericFocusOrder(2.0)),
    _ButtonItem(label: '我的钱包', order: NumericFocusOrder(3.0)),
    _ButtonItem(label: '消息中心', order: NumericFocusOrder(4.0)),
    _ButtonItem(label: '退出登录', order: null),
  ];

  /// 当前 primaryFocus 的 debugLabel，驱动调试浮层显示。
  /// 用 [ValueNotifier] + [ValueListenableBuilder] 局部重建，
  /// 避免 setState 全树重建触发 AppBar 重新应用 SystemUiOverlayStyle。
  final ValueNotifier<String> _primaryFocusLabel = ValueNotifier('null');

  /// 外层 FocusTraversalGroup 的 SmartFocusTraversalPolicy 实例。
  /// 整个 body 共用此 policy，负责方向键的跨 scope 智能降级。
  final SmartFocusTraversalPolicy _parentPolicy = SmartFocusTraversalPolicy();

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
    _primaryFocusLabel.dispose();
    super.dispose();
  }

  void _onFocusChange() {
    _refreshFocusLabel();
  }

  /// **删除当前持有焦点的按钮**（场景 C 注入入口）。
  ///
  /// 逻辑：
  /// 1. 读取当前 primaryFocus 的 debugLabel。
  /// 2. 若该 label 匹配 [_rightButtons] 中某项，则 setState 移除。
  /// 3. 用 [WidgetsBinding.instance.addPostFrameCallback] 确保节点 dispose
  ///    在下一帧完成后才返回，保证后续方向键操作时焦点树已稳定。
  ///
  /// **FB007 测试入口**：此方法为 public，集成测试通过 `tester.state`
  /// 取 `PersonalCenterDemoPageState` 后调用此方法。
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
      // FocusNode dispose 会触发 FocusManager 通知 _onFocusChange；
      // 此处的赋值作为双保险（应对 listener 时序遗漏）。
      _refreshFocusLabel();
    });
  }

  /// 重置右侧 scope 的焦点记忆（调试浮层"重置记忆"回调）。
  void _onResetMemory() {
    final FocusScopeNode? scope = _rightScopeNode;
    if (scope == null) return;
    _parentPolicy.resetMemory(scope);
  }

  /// 打印右侧 scope 的 rect（调试浮层"打印 Rect"回调）。
  void _onPrintRect() {
    final FocusScopeNode? scope = _rightScopeNode;
    if (scope == null) return;
    debugPrint('[FocusDebug] 右侧 scope.rect = ${scope.rect}');
  }

  /// 取右侧 FocusScope 节点（若未挂载返回 null）。
  FocusScopeNode? get _rightScopeNode {
    final BuildContext? ctx = _rightScopeKey.currentContext;
    return ctx == null ? null : FocusScope.of(ctx);
  }

  /// 用最新的 primaryFocus.debugLabel 刷新调试浮层（空值过滤）。
  // ValueNotifier 自身对相同值不通知监听器，无需调用方短路。
  void _refreshFocusLabel() {
    if (!mounted) return;
    _primaryFocusLabel.value =
        FocusManager.instance.primaryFocus?.debugLabel ?? 'null';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('个人中心'),
        // scrolledUnderElevation/surfaceTintColor/backgroundColor 由
        // main.dart 的 appBarTheme 全局关闭，避免 M3 scrolledUnder 让
        // AppBar 在 body 滚动时变色（iOS 表现为状态栏颜色变化）。
        // 手动 leading：BackButton 设为不可聚焦。
        // 方向键（上/左键）默认会跨 scope 跳到 AppBar 的 BackButton，
        // 干扰 SmartFocusTraversalPolicy 验证；ExcludeFocus 过滤掉它。
        leading: ExcludeFocus(
          child: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () => Navigator.maybePop(context),
          ),
        ),
      ),
      // ── 外层 FocusTraversalGroup（FB007 修复）──
      // 整个 body 共用一个 SmartFocusTraversalPolicy：
      // 左导航 + 右内容区的 FocusNode 都属于同一个 FocusTraversalGroup，
      // `FocusTraversalGroup.of()` 始终返回此 policy。
      // 左导航的 nearestScope 是外层（根）scope，包含所有节点，
      // 方向键候选搜索能跨越区域边界找到右侧节点。
      body: FocusTraversalGroup(
        policy: _parentPolicy,
        child: Stack(
          fit: StackFit.expand,
          children: [
            Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                // ── 左导航（窄列）──
                // 不创建独立 FocusScope 和 FocusTraversalGroup：
                // 左导航的 FocusNode 直接属于外层 group + 外层 scope。
                Expanded(
                  flex: 1,
                  child: Container(
                    color: Colors.grey.withValues(alpha: 0.05),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: const <Widget>[
                        FocusableButton(label: '个人中心', autofocus: true),
                        SizedBox(height: 12),
                        FocusableButton(label: '设置'),
                        SizedBox(height: 12),
                        FocusableButton(label: '关于'),
                      ],
                    ),
                  ),
                ),
                // ── 右内容区（宽列）──
                // 保留独立 FocusScope（为 SmartFocusTraversalPolicy 记忆层服务），
                // 但不创建独立 FocusTraversalGroup。
                // 当方向键候选落在右侧 scope 时，_isCrossScope 检测到跨 scope，
                // 触发 _smartRequestFocus(rightScope) 执行三层降级。
                //
                // **布局修复（R002-FIX004）**：
                // Stack( fit: StackFit.expand ) + Row( crossAxisAlignment.stretch )
                // 让左右两区撑满 body 高度。
                // 修复前（默认 loose + center）：
                //   - 平板：右内容区按内容高度居中显示（问题2）
                //   - 手机：右内容区内容高度 > body 高度，溢出部分被 Scaffold 裁剪，
                //     "退出登录"焦点框底部看不到（问题1）
                Expanded(
                  flex: 2,
                  child: FocusScope(
                    key: _rightScopeKey,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 32, vertical: 24),
                      child: SingleChildScrollView(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            ..._rightButtons
                                .map((item) => Padding(
                                      padding:
                                          const EdgeInsets.only(bottom: 12),
                                      child: FocusableButton(
                                        label: item.label,
                                        order: item.order,
                                      ),
                                    )),
                            // 底部余量：最后一个按钮获焦时，focus 系统的
                            // ensureVisible 不会把节点完全滚入 viewport，
                            // 需要额外空间确保 border 底部不被 Clip.hardEdge 裁剪。
                            const SizedBox(height: 24),
                          ],
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
              child: ValueListenableBuilder<String>(
                valueListenable: _primaryFocusLabel,
                builder: (BuildContext context, String label, _) =>
                    FocusDebugOverlay(
                  primaryFocusLabel: label,
                  onDeleteCurrentFocus: onDeleteCurrentFocus,
                  onResetMemory: _onResetMemory,
                  onPrintRect: _onPrintRect,
                ),
              ),
            ),
          ],
        ),
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
