import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_logic/pages/personal_center_page.dart';

/// R002-FIX003 回归测试：边界节点垂直方向键不应跨列跳转。
///
/// 复现的两个失效路径（均已修复）：
/// 1. 全屏 FocusScopeNode（_ModalScopeState）rect 覆盖整屏，X 重叠判断对它无效，
///    成为唯一候选 → 焦点落到 scope 容器。
///    修复：_findDirectionalCandidate 候选排除 FocusScopeNode。
/// 2. 列隔离搜索无候选时回退 super.inDirection，super 不做 X 列隔离，
///    用 beam 算法跨列找到其他区域节点（关于→消息中心）。
///    修复：垂直方向无候选时不回退 super，返回 false（焦点停留）。
///
/// 这两个失效只有在"边界节点"（列内最顶/最底）按下方向键时才暴露——
/// 非边界节点有同列候选胜出，scope 容器和 super 都被比下去。所以必须测边界。
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> pumpApp(WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: PersonalCenterDemoPage()));
    await tester.pumpAndSettle();
  }

  void runDeviceTest(String deviceName, Size logicalSize, double dpr) {
    testWidgets('[$deviceName] 列内边界节点垂直键停留（FIX003）', (tester) async {
      tester.view.physicalSize = logicalSize * dpr;
      tester.view.devicePixelRatio = dpr;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await pumpApp(tester);

      // 个人中心 → 设置 → 关于
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, '设置');
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, '关于');

      // 关于（左导航最底部）按下键 → 应停留，不跳右内容区
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '关于',
        reason: '[$deviceName] 关于是左导航最底部，按下键应停留。'
            '修复前：跳到 _ModalScopeState scope 容器，或被 super 跨列移到"消息中心"。',
      );

      // 关于按上键 → 设置（回到列内）
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, '设置');
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, '个人中心');

      // 个人中心（左导航最顶部）按上键 → 应停留，不跨列
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus?.debugLabel,
        '个人中心',
        reason: '[$deviceName] 个人中心是最顶部，按上键应停留',
      );
    });
  }

  runDeviceTest('iPhone16-横屏', const Size(844, 390), 3.0);
  runDeviceTest('iPad-横屏', const Size(1024, 768), 2.0);
  runDeviceTest('默认800x600', const Size(800, 600), 1.0);
}
