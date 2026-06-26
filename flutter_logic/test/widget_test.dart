// 主入口冒烟测试：验证 PersonalCenterDemoPage 可挂载并渲染核心元素。
//
// 旧的 counter demo 测试在 main.dart 替换为 PersonalCenterDemoPage 后失效，
// 本测试只做"能启动、能渲染"的最小验证，不重复 FF005/FF006/FB007 已覆盖的场景。

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_logic/main.dart';

void main() {
  testWidgets('App 启动后渲染 PersonalCenterDemoPage 核心元素', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pump();

    // 个人中心标题（AppBar + 页面内文本各一处）
    expect(find.text('个人中心'), findsNWidgets(2));
    // 左导航首项（autofocus 焦点默认落点）
    expect(find.text('设置'), findsOneWidget);
    expect(find.text('关于'), findsOneWidget);
    // 右内容区优先级最高的按钮（NumericFocusOrder 1.0）
    expect(find.text('会员签到'), findsOneWidget);
    // 调试浮层按钮
    expect(find.text('删除当前焦点'), findsOneWidget);
    expect(find.text('重置记忆'), findsOneWidget);
    expect(find.text('打印 Rect'), findsOneWidget);
  });
}
