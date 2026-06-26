import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';

/// R002-FB007：焦点 demo 集成测试
///
/// 验证 PersonalCenterDemoPage 的三层降级焦点策略：
/// - 场景 A：首次进入右侧内容区，焦点落在 [NumericFocusOrder(1.0)] 的"会员签到"
/// - 场景 B：跨区域来回切换，焦点回到上次位置（记忆层）
/// - 场景 C：动态删除当前焦点节点，按方向键焦点不丢失（兜底层）
/// - 场景 D：左导航垂直方向键不跨区域（FIX001 列聚类隔离）
///
/// **FB007 修复后**：
/// - Finding 1 已修复：左导航第一项 `FocusableButton(autofocus: true)`
/// - Finding 2 已修复：整个 body 共用一个 `FocusTraversalGroup(SmartFocusTraversalPolicy)`，
///   子区域用 `FocusScope` 隔离记忆但不创建独立 group。
///   方向键通过真实 `sendKeyEvent` 即可跨区域。
///
/// **所有场景均用真实 `sendKeyEvent` 验证**，不再绕过调用 `smartRequestFocus`。
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  /// 辅助：启动 app，左导航第一项 autofocus 后焦点自动落在"个人中心"。
  Future<void> pumpApp(WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: PersonalCenterDemoPage()),
    );
    await tester.pumpAndSettle();
  }

  group('焦点 demo 四场景', () {
    /// 场景 A：首次从左导航按右键进入右侧内容区，焦点应精准落在优先级最高的"会员签到"。
    ///
    /// 验证点：
    /// 1. 真实方向键（sendKeyEvent arrowRight）能跨 FocusScope 边界
    /// 2. SmartFocusTraversalPolicy 的第 2 层"优先级"分支生效，
    ///    即 OrderedTraversalPolicy.findFirstFocus 命中 NumericFocusOrder(1.0)
    testWidgets('场景 A：首次进入优先级引导（真实方向键）', (tester) async {
      await pumpApp(tester);

      // 确认初始焦点在左侧导航（autofocus）
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '个人中心',
        reason: '初始焦点应在左侧导航第 1 项（autofocus）',
      );

      // 真实方向键：从左导航按右键进入右侧内容区
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();

      // 验证：焦点落在 NumericFocusOrder(1.0) 的"会员签到"
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '会员签到',
        reason: '首次按右键进入右侧，应走优先级层命中 order=1.0 的节点',
      );
    });

    /// 场景 B：跨区域来回切换，焦点应记住上次位置。
    ///
    /// 验证点：
    /// 1. 右侧按左键能跨回左侧导航
    /// 2. 左侧按右键回到右侧时，记忆层命中（FocusScopeNode.focusedChild）
    testWidgets('场景 B：跨区域焦点记忆（真实方向键）', (tester) async {
      await pumpApp(tester);

      // Step 1: 左导航按右键 → 右侧"会员签到"（优先级层）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '会员签到',
        reason: '首次进入右侧应走优先级层',
      );

      // Step 2: 同区域内按下键移到"账户信息"（几何就近）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '账户信息',
        reason: '同区域内按下键应移到下一个节点',
      );

      // Step 3: 右侧"账户信息"按左键 → 回到左侧导航（跨 scope）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        anyOf('个人中心', '设置', '关于'),
        reason: '按左键应跨回左侧导航',
      );

      // Step 4: 左侧按右键 → 回到右侧（记忆层应命中"账户信息"）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();

      // 验证：焦点回到"账户信息"（记忆命中），而非重新回到"会员签到"
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '账户信息',
        reason: '跨区域来回切换，焦点应记住上次位置（记忆层命中）',
      );
    });

    /// 场景 C：动态删除当前焦点节点，按方向键后焦点不丢失。
    ///
    /// 验证点：
    /// 1. 删除节点后真实方向键仍能工作
    /// 2. 被删除节点的 canRequestFocus=false，记忆层失效
    /// 3. 策略引擎走优先级层找到下一个可用节点
    testWidgets('场景 C：动态删除当前焦点健壮兜底（真实方向键）', (tester) async {
      await pumpApp(tester);

      // 焦点放到右侧"会员签到"
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '会员签到',
      );

      // 通过 FB005 暴露的测试入口触发删除
      final PersonalCenterDemoPageState pageState = tester.state(
        find.byType(PersonalCenterDemoPage),
      ) as PersonalCenterDemoPageState;
      pageState.onDeleteCurrentFocus();

      // 等 setState + addPostFrameCallback 完成，节点 dispose 生效
      await tester.pumpAndSettle();
      await tester.pumpAndSettle();

      // 真实方向键：按右键（或上/下键）触发兜底逻辑
      // 此时焦点可能在左侧导航（"会员签到"被删除后焦点回退）
      // 无论焦点在哪，按右键应能找到右侧剩余节点
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();

      // 验证：焦点未丢失
      expect(
        FocusManager.instance.primaryFocus,
        isNotNull,
        reason: '删除当前焦点后，方向键应找到兜底节点',
      );

      // 验证：焦点落到一个右侧剩余可用节点（场景 C 验证点：
      // analysis 流程图明确"焦点落到账户信息"，不应跳回左导航）
      final String? label = FocusManager.instance.primaryFocus?.debugLabel;
      expect(
        label,
        isNot('会员签到'),
        reason: '会员签到已被删除，不应再获得焦点',
      );
      expect(
        ['账户信息', '退出登录'].contains(label),
        isTrue,
        reason: '焦点应落在右侧剩余按钮上（账户信息/退出登录），实际落在: $label',
      );
    });

    /// 场景 D：左导航垂直方向键不跨区域（FIX001 列聚类隔离）。
    ///
    /// 验证点：
    /// 1. 左导航内部按上下键，焦点只在左导航 3 个按钮间移动
    /// 2. 不会因几何就近跳到右内容区（同行 Y 距离=0 的节点）
    testWidgets('场景 D：左导航垂直键不跨区域（FIX001 列隔离）', (tester) async {
      await pumpApp(tester);

      // 初始焦点在"个人中心"
      expect(FocusManager.instance.primaryFocus?.debugLabel, '个人中心');

      // 按下键 → 应到"设置"（同列），不跳右内容区
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '设置',
        reason: '左导航按下键应到同列下一个按钮，不跳到右内容区',
      );

      // 再按下键 → 应到"关于"（同列），不跳右内容区
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '关于',
        reason: '左导航连续按下键应在同列内移动',
      );
    });
  });
}
