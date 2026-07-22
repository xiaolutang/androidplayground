---
version: "1.0"
type: tasks
topic: landscape-save-management
requirement_cycle: R005
workflow:
  evaluate_provider: local
  mode: auto
status: planned
---

# 横版手柄存档管理二级页面 — Flutter 任务清单

基于 `.dev-flow/R005/analysis/2026-07-21--landscape-save-management.md`。将 analysis 的 4 节点收敛为 3 个任务：analysis 的 FF001（SaveSlot 模型）无独立 UI 渲染，降为 FB001 的子任务 FB001.1，避免给纯数据模型强加 visual-verify。

## 全局约束

- **技术栈**：Flutter（flutter_logic/ 模块），Add-to-App 不变量 INV-1，纯前端无跨层通信
- **风格参考**：严格对齐 codex 已实现的 `view/layout_switch_overlay.dart`（蒙层 0xCC121A29 + CallbackShortcuts ESC + FocusTraversalGroup + FocusableActionDetector + FocusRing + _BackTitle 返回样式）
- **画布**：844×390 横屏（FittedBox contain，与 landscape_page 一致）
- **字体**：`AlibabaPuHuiTi`（已在 golden test 注册 Heavy + Regular）
- **禁止**：不引入新依赖；不改 architecture.md；不动竖版 portrait_page；不实现真实存档持久化
- **状态管理**：页面级 StatefulWidget（与 LayoutSwitchOverlay 同级），不引入 Provider/Bloc

## 执行顺序

1. ⬜ R005-FB001 — SaveManagementOverlay 二级页（含 SaveSlot 模型 + mock + 资源下载 + 面板 + 状态管理 + 焦点）（无依赖）
   - ⬜ FB001.0 下载图标/缩略图资源
   - ⬜ FB001.1 SaveSlot 领域模型 + mock 数据
   - ⬜ FB001.2 overlay 容器（蒙层 + 面板 + 返回 + 滚动条）
   - ⬜ FB001.3 两区布局 + 有状态增删保存读取
2. ⬜ R005-FB002 — SaveSlotCard 槽位卡片组件（依赖 FB001.1）
3. ⬜ R005-FF002 — landscape 挂载接入 + golden/行为测试（依赖 FB001、FB002）
4. ⬜ 最后 — `flutter analyze` + `flutter test test/gamepad_app/` 全绿

---

## R005-FB001：SaveManagementOverlay 二级页 `⬜ 待处理`

- 文件：`flutter_logic/lib/gamepad_app/view/save_management_overlay.dart`（新建）
- 资源：`flutter_logic/assets/gamepad_app/ic_delete.svg`、`save_thumb_a.png`、`save_thumb_b.png`（新建）
- 改动类型：新建
- domain: ui
- task_layer: business
- depends_on: []
- priority: 5
- risk_tags: [focus, stateful]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - 实现 5 个稳定标识（save_mgmt.panel / save_mgmt.back_button / save_mgmt.scrollbar / save_mgmt.quick_section / save_mgmt.manual_section，清单见 AcceptanceSpec）
  - visual-verify PASS（三层证据对照 AcceptanceSpec）
  - 固化 visual_baseline（见下方 yaml）
  - 蒙层 0xCC121A29 覆盖 844×390；面板 443×282@(201,26) 圆角 24 径向渐变
  - 返回按钮回菜单（onBack）；ESC 等价返回；蒙层点击 onDismiss
  - 删除手动槽 → 列表收缩、槽数减少；保存 → 时间刷新；读取 → onLoad 回调
  - autofocus 落到返回按钮
- test_tasks:
  - type: integration
    layer: integration
    domain: flutter
    description: overlay 打开/返回/删除/保存/读取端到端
    scenarios: [打开, 返回回菜单, 删除移除, 保存刷新时间, logo dismiss]
    deferred: false
- contract_refs: []
- decision_refs: []
- blocked_files: [flutter_logic/lib/gamepad_app/portrait_page.dart]

### FB001.0 下载图标/缩略图资源 `⬜`

从 Figma node 3448:30090 的 design_context 资源 URL 下载到 `assets/gamepad_app/`：

- `ic_delete.svg` ← Figma asset `imgUnion`（https://www.figma.com/api/mcp/asset/b218c45d-092a-4cf7-aab1-6d35e0cc20ac），用 `download_assets` 取 SVG 或自行转 svg
- `save_thumb_a.png` ← `imgRectangle462286322`（9db65d9d-...）
- `save_thumb_b.png` ← `imgRectangle462286323`（bea334e1-...）

返回箭头复用已有 `layout_back.svg`，不新建 ic_back。assets/gamepad_app/ 已在 pubspec 注册，无需改 pubspec。

### FB001.1 SaveSlot 领域模型 + mock 数据 `⬜`

写在 `save_management_overlay.dart` 顶部（同文件，模型 + overlay 一起，避免文件爆炸）。

```dart
enum SaveSlotKind { quick, manual }

@immutable
class SaveSlot {
  const SaveSlot({
    required this.id,
    required this.title,
    required this.kind,
    required this.time,
    required this.thumbAsset,
  });
  final String id;        // 'q1' / 'm1' / 'm2'
  final String title;     // '最近快存' / '存档1'
  final SaveSlotKind kind;
  final String time;      // '2026-07-02 14:32'
  final String thumbAsset;// 'assets/gamepad_app/save_thumb_a.png'
}
```

mock 初值（State 初字段）：
- `_quickSlot = SaveSlot(id:'q1', title:'最近快存', kind:quick, time:'2026-07-02 14:32', thumb:'save_thumb_a.png')`
- `_manualSlots = [存档1(save_thumb_a), 存档2(save_thumb_b)]`

### FB001.2 overlay 容器（蒙层 + 面板 + 返回 + 滚动条） `⬜`

```dart
class SaveManagementOverlay extends StatefulWidget {
  const SaveManagementOverlay({
    super.key,
    required this.onBack,     // 返回 → 回菜单
    required this.onDismiss,  // 蒙层点击/logo → dismiss 全部
  });
  final VoidCallback onBack;
  final VoidCallback onDismiss;
  @override State<SaveManagementOverlay> createState() => _SaveManagementOverlayState();
}
```

build 骨架（对齐 LayoutSwitchOverlay）：

```dart
CallbackShortcuts(
  bindings: { SingleActivator(Escape): onBack },
  child: FocusTraversalGroup(
    policy: WidgetOrderTraversalPolicy(),
    child: Stack(children: [
      Positioned.fill(GestureDetector(  // 蒙层
        key: ValueKey('save_mgmt-scrim'),
        behavior: HitTestBehavior.opaque,
        onTap: onDismiss,
        child: ColoredBox(color: Color(0xCC121A29)),
      )),
      Positioned(                       // 面板 443×282@(201,26)
        key: ValueKey('save_mgmt.panel'),
        left: 201, top: 26, width: 443, height: 282,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            gradient: RadialGradient(
              center: Alignment(0, -0.7), radius: 1.2,
              colors: [Color(0xFFF1EDFD), Color(0xFFF6FAFF), Color(0xFFFFFFFF)],
              stops: [0, 0.215, 1.0],
            ),
          ),
          child: Stack(children: [
            Positioned(left:16, top:16, child: _BackTitle(onPressed: onBack)), // key 'save_mgmt.back_button'
            Positioned(left:16, right:16, top:56, height:210, child: _body()),  // 两区
            Positioned(right:8, top: ... , child: _scrollbar()),                 // key 'save_mgmt.scrollbar' 6×56 #d4deef
          ]),
        ),
      ),
    ]),
  ),
)
```

`_BackTitle`：复用 layout_switch_overlay 的 _BackTitle 样式（layout_back.svg 8.4×14 + 文字），文字改「存档管理」14px #6a7691。提取为 overlay 内私有 widget 或抽公共。可考虑把 layout_switch 的 _BackTitle 提为 `view/layer/back_title.dart` 共享（轻量重构，两个 overlay 复用）。

`_scrollbar`：`Container(width:6, height:56, decoration: BoxDecoration(color: Color(0xFFD4DEEF), borderRadius: 4))`，纯视觉占位（预留 Scrollable 扩展）。

### FB001.3 两区布局 + 有状态增删保存读取 `⬜`

`_SaveManagementOverlayState`：

```dart
SaveSlot? _quickSlot;            // null → 快存空态"暂无快存"
late List<SaveSlot> _manualSlots;

void _removeSlot(String id) => setState(() {
  if (id == _quickSlot?.id) { _quickSlot = null; return; }
  _manualSlots.removeWhere((s) => s.id == id);
});
void _saveSlot(String id) => setState(() {
  // manual：更新 time；quick：覆盖最近快存 time
  _manualSlots = _manualSlots.map((s)=> s.id==id ? s.copyWith(time:'刚刚') : s).toList();
});
void _loadSlot(String id) { /* demo：仅触发回调/日志，无副作用 */ }
```

`_body()` → Column(gap8)：
- 快速存档区（key 'save_mgmt.quick_section'）：表头 `_SectionHeader(left:'快速存档', right:['删除'])` + 若 `_quickSlot!=null` 一个 `SaveSlotCard(slot, onDelete)`，否则空态文字「暂无快存」
- 手动存档区（key 'save_mgmt.manual_section'）：表头 `_SectionHeader(left:'手动存档', right:['读取','覆盖','删除'])` + `_manualSlots` 为空时空态，否则 Column(gap8) of `SaveSlotCard(slot, onSave, onLoad, onDelete)`

`SaveSlot.copyWith` 补一个。`_SectionHeader`：Row(justify:spaceBetween, px8, h18, 文字 14px #6a7691 lh18)。

---

## R005-FB002：SaveSlotCard 槽位卡片组件 `⬜ 待处理`

- 文件：`flutter_logic/lib/gamepad_app/view/layer/save_slot_card.dart`（新建）
- 改动类型：新建
- domain: ui
- task_layer: business
- depends_on: [R005-FB001]
- priority: 4
- risk_tags: [focus]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - 实现 7 个稳定标识（save_mgmt.slot.card / .thumb / .title / .time / .delete / .save / .load）
  - visual-verify PASS（三层证据对照 AcceptanceSpec）
  - 固化 visual_baseline（见下方 yaml）
  - 卡片 411 宽（面板内边距后），bg #e7edf8 圆角 8 padding 8；缩略图 71×40 圆角 4；标题 14px Heavy #121a29；时间 12px #6a7691
  - quick 槽只渲染 delete；manual 槽渲染 save+load+delete 三按钮
  - 每个按钮可聚焦（FocusableActionDetector）+ Enter/Space 激活 + FocusRing
- test_tasks:
  - type: unit
    layer: unit
    domain: flutter
    description: SaveSlotCard quick/manual 两种 kind 的按钮渲染与激活
    scenarios: [quick 只 delete, manual 三按钮, 按钮激活回调]
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FB002.1 卡片结构与操作按钮 `⬜`

```dart
class SaveSlotCard extends StatelessWidget {
  const SaveSlotCard({
    super.key,
    required this.slot,
    required this.onDelete,
    this.onSave, this.onLoad, this.autofocus = false,
  });
  final SaveSlot slot;
  final VoidCallback onDelete;
  final VoidCallback? onSave;   // null = quick 槽不显示
  final VoidCallback? onLoad;
  final bool autofocus;

  @override Widget build(BuildContext context) {
    return Container(
      key: ValueKey('save_mgmt.slot.card'),
      width: 411,
      decoration: BoxDecoration(color: Color(0xFFE7EDF8), borderRadius: 8),
      padding: EdgeInsets.all(8),
      child: Row(children: [
        ClipRRect(borderRadius: 4, child: Image.asset(slot.thumbAsset, width:71, height:40, fit: cover)), // key .thumb
        SizedBox(width:8),
        Expanded(Column(crossAxisAlignment:start, children: [
          Text(slot.title, 标题样式 14 Heavy #121a29),  // key .title
          Text(slot.time, 12 Regular #6a7691),          // key .time
        ])),
        Row(gap16, children: [
          if (onSave!=null) _IconBtn(icon:'ic_save.svg', semantic:'保存', onPressed:onSave!, key:.save),
          if (onLoad!=null) _IconBtn(icon:'ic_load.svg', semantic:'读取', onPressed:onLoad!, key:.load),
          _IconBtn(icon:'ic_delete.svg', semantic:'删除', onPressed:onDelete, key:.delete),
        ]),
      ]),
    );
  }
}
```

`_IconBtn`：40×40 ghost button 圆角 4，内 24×24 SvgPicture（srcIn 可不变色或按 LayoutChoiceCard 的 FocusRing 模式）。复用 `FocusableActionDetector` + Enter/Space ActivateIntent + `FocusRing(borderRadius:4)`（focused 态）。参考 `layout_switch_overlay.dart` 的 `LayoutChoiceCard` 焦点实现。

---

## R005-FF002：landscape 挂载接入 + golden/行为测试 `⬜ 待处理`

- 文件：`flutter_logic/lib/gamepad_app/landscape_page.dart`（修改）、`flutter_logic/test/gamepad_app/landscape_golden_test.dart`（修改）
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: [R005-FB001, R005-FB002]
- priority: 5
- risk_tags: [regression]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - 菜单点 saveManagement → MenuOverlay 消失 + SaveManagementOverlay 出现
  - 返回按钮/ESC → 回菜单（MenuOverlay 出现，焦点回存档管理项）
  - logo 按钮 → 两个 overlay 都消失
  - golden `landscape_save_management.png` 生成且视觉对齐 Figma 3448:30090
  - 删除手动槽 → SaveSlotCard 数量减少；保存 → 时间文字变化
  - 现有 landscape 测试全部仍通过（不回归）
- test_tasks:
  - type: integration
    layer: integration
    domain: flutter
    description: 挂载端到端 + golden 回归
    scenarios: [打开 overlay, 返回回菜单, logo dismiss, 删除移除, golden 匹配]
- contract_refs: []
- decision_refs: []
- blocked_files: [flutter_logic/lib/gamepad_app/portrait_page.dart]

### FF002.1 GamepadLandscapePage 状态与参数 `⬜`

```dart
// 新增 dart-define 开关（与 menu/layout 一致）
const bool _initialLandscapeSaveMgmtOpen =
    bool.fromEnvironment('gamepadLandscapeSaveMgmtOpen', defaultValue: false);

class GamepadLandscapePage {
  // 新增入参
  final bool initialSaveManagementOpen;
  // 默认值 = _initialLandscapeSaveMgmtOpen
}

class _GamepadLandscapePageState {
  late bool _saveManagementOpen;
  @override void initState() {
    ...
    _saveManagementOpen = widget.initialSaveManagementOpen && !_menuOpen && !_layoutOpen;
  }
}
```

### FF002.2 _selectMenuItem 分支 + 互斥 `⬜`

```dart
void _selectMenuItem(MenuAction action) {
  widget.onMenuSelected?.call(action);
  if (action == MenuAction.switchLayout) { ... 现有 ... }
  else if (action == MenuAction.saveManagement) {
    setState(() { _menuOpen = false; _saveManagementOpen = true; });
  }
  else if (action == MenuAction.continueGame) { _closeMenu(); }
}
```

`_toggleMenu`：打开菜单时关闭 saveManagement（`_saveManagementOpen = false`），与 layout 互斥逻辑对称。
`_dismissOverlays`：追加 `_saveManagementOpen = false`。
新增 `_backFromSaveMgmt`：`setState(() { _saveManagementOpen = false; _menuOpen = true; })`（复用 _backToMenu 模式，或合并 _backToMenu 同时处理 layout/saveMgmt）。

### FF002.3 _LandscapeCanvas 渲染分支 `⬜`

`_LandscapeCanvas` 新增字段 `final bool saveManagementOpen;`，build 内 overlayOpen 判定改为 `menuOpen || layoutOpen || saveManagementOpen`，新增：

```dart
if (saveManagementOpen)
  Positioned.fill(child: SaveManagementOverlay(
    onBack: onBackFromSaveMgmt,
    onDismiss: onDismissOverlays,
  )),
```

### FF002.4 测试：pumpLandscape 加参 + golden + 行为 `⬜`

`pumpLandscape` 加 `bool initialSaveManagementOpen = false`。新增测试：

```dart
testWidgets('save management menu action opens the overlay', (tester) async {
  await pumpLandscape(tester, initialMenuOpen: true);
  await tester.tap(find.byKey(ValueKey(MenuAction.saveManagement)));
  await tester.pump();
  expect(find.byType(MenuOverlay), findsNothing);
  expect(find.byType(SaveManagementOverlay), findsOneWidget);
  expect(find.byType(SaveSlotCard), findsNWidgets(3)); // 1 quick + 2 manual
});

testWidgets('save management matches Figma frame', (tester) async {
  await pumpLandscape(tester, initialSaveManagementOpen: true);
  await precacheImage(SaveSlotCard 缩略图...);
  await expectLater(find.byType(GamepadLandscapePage),
      matchesGoldenFile('landscape_save_management.png'));
});

testWidgets('delete removes a manual slot', (tester) async {
  await pumpLandscape(tester, initialSaveManagementOpen: true);
  await tester.tap(find.byKey(ValueKey('save_mgmt.slot.delete')).last); // 手动槽删除
  await tester.pump();
  expect(find.byType(SaveSlotCard), findsNWidgets(2));
});

testWidgets('back returns to menu, logo dismisses all', (tester) async {
  await pumpLandscape(tester, initialSaveManagementOpen: true);
  await tester.tap(find.text('存档管理')); // 返回按钮
  await tester.pump();
  expect(find.byType(MenuOverlay), findsOneWidget);
  // logo dismiss 走现有 landscape-logo-button 测试模式
});
```

---

## visual_baseline（FB001 / FB002 共享）

```yaml
visual_baseline:
  source:
    figma_url: https://www.figma.com/design/QsMNPF0eTLlc2A0h1rTuAT/pantas--launcher-flutter?node-id=3448-30090
    frame_id: 3448:30090
  device_profile:
    platform: flutter_test
    width_px: 844
    height_px: 390
    pixel_ratio: 1
  assertions:
    - 面板 443×282@(201,26) 圆角 24 径向渐变 #f1edfd→#f6faff→#fff
    - 蒙层 0xCC121A29 全屏
    - 返回按钮@(16,16) ghost 圆角16 + layout_back.svg + "存档管理" 14px #6a7691
    - 快速存档区：表头(快速存档|删除) + 1 槽（最近快存）
    - 手动存档区：表头(手动存档|读取 覆盖 删除) + 2 槽（save/load/delete）
    - 槽：411宽 bg#e7edf8 圆角8 padding8；缩略图71×40 圆角4；标题14px Heavy #121a29；时间12px #6a7691
    - 操作按钮 40×40 ghost 圆角4，图标24×24
    - 右侧滚动条 6×56 #d4deef 圆角4
    - 底部 expand(514,336) + logo(303,336) 圆按钮浮在蒙层上
  thresholds:
    layout_tolerance_px: 2
    spacing_tolerance_px: 2
    font_size_tolerance_px: 0.5
    color_delta_e: 3
    screenshot_match_threshold: 0.95
```
