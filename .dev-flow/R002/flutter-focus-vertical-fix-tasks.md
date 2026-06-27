---
version: "1.0"
type: tasks
topic: flutter-focus-vertical-fix
requirement_cycle: R002
workflow:
  evaluate_provider: local
  mode: auto
status: planned
---

# Flutter 焦点垂直键列隔离 Bug Fix — 任务清单

基于 [brainstorm 结论](analysis/brainstorm-2026-06-27--vertical-key-scope-isolation.md)，修复左导航上下键焦点跨区域跳转 bug。

## 全局约束

- **只改 `_findDirectionalCandidate` 一个方法**，不改 scope 结构、不改 FocusTraversalGroup 结构、不改跨 scope 三层降级逻辑
- **不破坏已有测试**：28 unit + 3 integration 必须全绿
- **水平方向键行为不变**：左/右键的候选搜索仍在整个 scope 内按 X 轴距离排序

## 执行顺序

1. ✅ R002-FIX001 — `_findDirectionalCandidate` 垂直方向 X 重叠过滤
2. ✅ R002-FIX002 — FocusableButton 移除 AnimatedScale（焦点框裁剪修复）
3. ⬜ 最后 — 全量测试验证

---

## R002-FIX001：smart_focus_policy.dart — 垂直方向列聚类过滤 `✅ 已完成`

- 文件：`flutter_logic/lib/focus/smart_focus_policy.dart`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 垂直方向键（up/down）时，候选节点 rect 与 anchor rect 在 X 轴上有水平重叠（区间相交），才参与排序
  - 水平方向键（left/right）行为完全不变（无 X 重叠过滤）
  - 左导航"设置"按下键 → 焦点到"关于"，不跳到右内容区
  - 左导航"关于"按下键 → 无候选（到底部），停留不动
  - 右内容区上下键行为不变（已有 FocusScope，本身就在同列）
  - `flutter analyze` 无 error
  - `flutter test` 28+ 用例全通过
  - `flutter test integration_test/` 4 场景全通过
- status: completed
- commit: 95025850（fix）/ e8691fde（场景 D 测试）
- evidence: iPhone 16 模拟器集成测试诊断日志验证 — "设置"rect=[16,268]，
  右侧按钮 left≈316 ≥ 268 → 被 X 重叠过滤跳过，候选正确命中"关于"

---

## R002-FIX002：focusable_button.dart — 移除 AnimatedScale 修复焦点框裁剪 `✅ 已完成`

- 文件：`flutter_logic/lib/focus/focusable_button.dart`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: completed
- 背景：右内容区按钮被 `CrossAxisAlignment.stretch` 拉到
  `SingleChildScrollView` 全宽，`AnimatedScale(1.05)` 放大后左右各超出 2.5%，
  被 `SingleChildScrollView` 默认 `Clip.hardEdge` 裁剪 → 焦点蓝色边框左右"被吃"。
- 修复：移除 `AnimatedScale`，焦点高亮仅依赖边框(2px blue) + 背景色(0.12 alpha) +
  字重(FontWeight.w600)。视觉足够明显且零裁剪风险。
- acceptance_criteria:
  - 焦点态边框完整显示，无左右裁剪
  - 非焦点态边框透明（无边框残留）
  - `flutter analyze` 无 error
  - 场景1/场景2 widget 测试更新（去掉 scale 断言，保留边框断言）
  - 全量测试通过
- test_updates:
  - focusable_button_test.dart 场景1：标题改为"获得焦点时 Container 有蓝色边框（宽度 2）"，去掉 AnimatedScale 断言
  - focusable_button_test.dart 场景2：标题改为"失去焦点时边框透明"，去掉 scale 断言
- test_tasks:
  - type: unit
    description: 垂直方向 X 重叠过滤验证
    scenarios:
      - 左导航"设置"按下键 → 候选为"关于"（同列），非右内容区"账户信息"
      - 左导航"个人中心"按上键 → 无候选（最顶部）
      - 右内容区"会员签到"按下键 → 候选为"账户信息"（同列）
      - 水平方向不受过滤影响：左导航"设置"按右键 → 候选仍为右内容区节点
- contract_refs: []
- decision_refs: []
- blocked_files: []

### FIX001.1 垂直方向 X 重叠过滤 `⬜`

在 `_findDirectionalCandidate`（当前 `smart_focus_policy.dart:172-232`）的 switch 分支中，为 `TraversalDirection.up` 和 `TraversalDirection.down` 增加列聚类判断：

```dart
// 在 forward 判断之后、距离比较之前，增加垂直方向的同列过滤
if (!forward) continue;

// 列聚类：垂直方向键时，只保留与 anchor 在 X 轴上有水平重叠的候选
if (direction == TraversalDirection.up ||
    direction == TraversalDirection.down) {
  // 水平区间不相交 → 不同列 → 跳过
  if (r.left >= anchorRect.right || r.right <= anchorRect.left) {
    continue;
  }
}
```

**关键**：
- 用 rect 的水平区间相交判断（`r.left < anchorRect.right && r.right > anchorRect.left`），而非中心点距离
- 这样宽窄不同的按钮也能正确聚类（左导航窄列与右内容区宽列 X 区间不重叠）
- 只对 up/down 方向生效，left/right 不受影响

### FIX001.2 补充垂直列隔离单元测试 `⬜`

在 `test/focus/smart_focus_policy_test.dart` 的 `Finding 5.3: _findDirectionalCandidate 方向候选算法` group 中追加用例：

```dart
testWidgets('垂直方向列隔离 — 左列下键不跳到右列', (tester) async {
  final harness = await buildDirectionalHarness(
    tester,
    layout: [
      // 左列
      (label: 'L1', left: 0,   top: 0,   w: 100, h: 40),
      (label: 'L2', left: 0,   top: 100, w: 100, h: 40),
      // 右列（与左列同行，X 不重叠）
      (label: 'R1', left: 200, top: 0,   w: 100, h: 40),
      (label: 'R2', left: 200, top: 100, w: 100, h: 40),
    ],
  );

  // L1 按下键 → 候选应为 L2（同列），非 R2（同行但不同列）
  final candidate = harness.policy.findDirectionalCandidateForTest(
    harness.scopeRef, harness.nodes[0], TraversalDirection.down,
  );
  expect(candidate?.debugLabel, 'L2');
});

testWidgets('水平方向不受列隔离 — 左列右键仍找到右列', (tester) async {
  // 同上布局
  // L1 按右键 → 候选应为 R1（水平方向不受 X 重叠过滤）
  final candidate = harness.policy.findDirectionalCandidateForTest(
    harness.scopeRef, harness.nodes[0], TraversalDirection.right,
  );
  expect(candidate?.debugLabel, 'R1');
});
```

### FIX001.3 运行全量测试验证 `⬜`

```bash
cd flutter_logic
flutter analyze
flutter test
flutter test integration_test/
```

**验收**：全部通过，无 regression。

---

## 最后：全量测试验证 `✅ 已完成`

### 自动化测试

```bash
cd flutter_logic
flutter analyze                        # 无 error
flutter test                           # 30 单元 + widget 测试全通过
flutter test integration_test/         # 4 场景集成测试全通过
```

### 手动验证（iPhone 16 模拟器横屏，GLM-5V-Turbo 视觉验收）

- **FIX001（垂直列隔离）**：从"个人中心"按下键 ×2 → 焦点依次到"设置"→"关于"，全程留在左导航列，**未跳到右内容区**。✅
- **FIX002（焦点框无裁剪）**：右侧"会员签到"获得焦点时，蓝色边框（2px）四周完整显示，**左右无被吃边**。✅
- 三层降级（左导航"个人中心"按右键 → 右内容区"会员签到"）行为不变。✅

### Evidence

- FIX001 集成测试诊断日志：iPhone 16 "设置"rect=[16,268]，右侧按钮 left≈316 ≥ 268 → X 重叠过滤跳过，候选正确命中"关于"。
- FIX002 视觉验收截图（GLM-5V-Turbo 分析）：
  - `https://litter.catbox.moe/oa75v9.png` — 右侧焦点态，边框完整
  - `https://litter.catbox.moe/erasi5.png` — 左导航"关于"焦点态，列隔离生效
