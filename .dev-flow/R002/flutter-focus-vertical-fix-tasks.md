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

1. ⬜ R002-FIX001 — `_findDirectionalCandidate` 垂直方向 X 重叠过滤
2. ⬜ 最后 — 全量测试验证

---

## R002-FIX001：smart_focus_policy.dart — 垂直方向列聚类过滤 `⬜ 待处理`

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
  - `flutter test integration_test/` 3 场景全通过
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

## 最后：全量测试验证 `⬜ 待处理`

依赖 R002-FIX001 完成后执行。

### 验证步骤

```bash
cd flutter_logic
flutter analyze                        # 无 error
flutter test                           # 单元 + widget 测试全通过（含新增用例）
flutter test integration_test/         # 集成测试 3 场景全通过
```

### 手动验证（iOS 模拟器横屏）

1. 焦点在左导航"设置" → 按下键 → 焦点到"关于"（不到右内容区）
2. 焦点在左导航"关于" → 按下键 → 焦点停留不动
3. 焦点在左导航"个人中心" → 按右键 → 焦点到右内容区"会员签到"（三层降级不变）
4. 场景 B 记忆、场景 C 兜底行为不变
