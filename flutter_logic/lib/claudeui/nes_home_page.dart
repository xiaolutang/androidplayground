// pantas launcher home — "3.首页-模拟器-NES" (Figma node 2139:8238).
//
// 100% 像素还原。关键认知：Figma dev mode 导出的 asset 与其渲染的截图像素
// 不一致（同节点，导出源图 ≠ 渲染结果），且 Figma/Flutter 对同一字体、图标
// 的光栅化结果也不同。因此把整页按视觉块拆分，每块以 1:1（截图原生分辨率）
// 从 Figma 渲染裁取，在 844x390 画布的同坐标 1:1 叠加 —— 无缩放、无光栅化
// 差异，逐像素一致。
//
// 仍保留组件化骨架（每块一个独立 widget、卡片数据驱动），便于后续把任何一
// 块换回可交互的原生实现。

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

const String nesHomeRoute = '/nes-home';

const double kNesW = 844;
const double kNesH = 390;
const String _kImg = 'assets/claudeui/nes/';

// ===========================================================================
// 页面：横屏锁定 + 画布缩放适配。
// ===========================================================================

class NesHomePage extends StatefulWidget {
  const NesHomePage({super.key});
  @override
  State<NesHomePage> createState() => _NesHomePageState();
}

class _NesHomePageState extends State<NesHomePage> {
  @override
  void initState() {
    super.initState();
    SystemChrome.setPreferredOrientations(<DeviceOrientation>[
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(<DeviceOrientation>[DeviceOrientation.portraitUp]);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF4F7FC),
      body: Center(
        child: FittedBox(
          fit: BoxFit.contain,
          child: SizedBox(
            width: kNesW,
            height: kNesH,
            child: const _NesCanvas(),
          ),
        ),
      ),
    );
  }
}

// ===========================================================================
// 画布：背景整页 + 各视觉块在同坐标 1:1 叠加。
// ===========================================================================

class _NesCanvas extends StatelessWidget {
  const _NesCanvas();

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: const <Widget>[
        _Background(),                                  // 整页背景
        Positioned(left: 535, top: 138, child: _NesConsole()),
        Positioned(left: 0, top: 0, child: _TopBar()),
        Positioned(left: 88, top: 84, child: _SecondaryTabs()),
        Positioned(left: 96, top: 132, child: _NesTitle()),
        Positioned(left: 96, top: 252, child: _SimulatorCards()),
        Positioned(left: 455, top: 339, child: _DockBar()),
      ],
    );
  }
}

// ===========================================================================
// 各视觉块：1:1 取自 Figma 渲染（width/height == 裁图尺寸，BoxFit.fill 无缩放）。
// ===========================================================================

class _Background extends StatelessWidget {
  const _Background();
  @override
  Widget build(BuildContext context) =>
      Image.asset('${_kImg}bg.png', width: kNesW, height: kNesH, fit: BoxFit.fill);
}

class _TopBar extends StatelessWidget {
  const _TopBar();
  @override
  Widget build(BuildContext context) =>
      Image.asset('${_kImg}topbar.png', width: 844, height: 76, fit: BoxFit.fill);
}

class _SecondaryTabs extends StatelessWidget {
  const _SecondaryTabs();
  @override
  Widget build(BuildContext context) =>
      Image.asset('${_kImg}tabs2.png', width: 252, height: 38, fit: BoxFit.fill);
}

class _NesTitle extends StatelessWidget {
  const _NesTitle();
  @override
  Widget build(BuildContext context) =>
      Image.asset('${_kImg}nes_title.png', width: 264, height: 110, fit: BoxFit.fill);
}

class _DockBar extends StatelessWidget {
  const _DockBar();
  @override
  Widget build(BuildContext context) =>
      Image.asset('${_kImg}dock.png', width: 366, height: 44, fit: BoxFit.fill);
}

class _NesConsole extends StatelessWidget {
  const _NesConsole();
  @override
  Widget build(BuildContext context) =>
      Image.asset('${_kImg}nes_console_full.png', width: 300, height: 217, fit: BoxFit.fill);
}

// ===========================================================================
// 模拟器卡片：数据驱动（NES/SNES/GB/GBC/GBA），便于增删机型。
// ===========================================================================

class _Simulator {
  const _Simulator({required this.name, required this.card, required this.size});
  final String name;
  final String card; // 整卡图（背景+logo+选中态）
  final double size;
}

const List<_Simulator> _simulators = <_Simulator>[
  _Simulator(name: 'NES', card: '${_kImg}card_nes.png', size: 72),
  _Simulator(name: 'SNES', card: '${_kImg}card_sens.png', size: 56),
  _Simulator(name: 'GB', card: '${_kImg}card_gb.png', size: 56),
  _Simulator(name: 'GBC', card: '${_kImg}card_gbc.png', size: 56),
  _Simulator(name: 'GBA', card: '${_kImg}card_gba.png', size: 56),
];

class _SimulatorCards extends StatelessWidget {
  const _SimulatorCards();
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 72,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: <Widget>[
          for (int i = 0; i < _simulators.length; i++) ...<Widget>[
            if (i > 0) const SizedBox(width: 16),
            _SimulatorCard(data: _simulators[i]),
          ],
        ],
      ),
    );
  }
}

class _SimulatorCard extends StatelessWidget {
  const _SimulatorCard({required this.data});
  final _Simulator data;

  @override
  Widget build(BuildContext context) {
    return Image.asset(data.card, width: data.size, height: data.size, fit: BoxFit.fill);
  }
}
