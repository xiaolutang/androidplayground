---
version: "1.0"
type: tasks
topic: playground-home
requirement_cycle: R003
workflow:
  evaluate_provider: local
  mode: auto
status: planned
---

# Flutter Playground 入口页 — 任务清单

基于 [brainstorm 结论](analysis/brainstorm-2026-06-27--playground-home.md)，为 playground 加总入口，把焦点 demo 作为其中一项。

## 全局约束

- **不动** `lib/pages/personal_center_page.dart`（AppBar 已存在）
- **不破坏** 现有 37 单元/widget 测试 + 4 集成测试
- **不引入** 第三方依赖

## 执行顺序

1. ⬜ R003-HM001 — 新增 `lib/home_page.dart`（ListView 入口）
2. ⬜ R003-HM002 — 改 `lib/main.dart`（注册 named routes + home=HomePage）
3. ⬜ R003-HM003 — 测试：入口页跳转 + 现有测试不破坏

---

## R003-HM001：lib/home_page.dart — 新增 HomePage（ListView 入口） `⬜`

- 文件：`flutter_logic/lib/home_page.dart`
- 改动类型：新增
- domain: ui
- task_layer: foundation
- depends_on: []
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - HomePage 是 StatelessWidget，Scaffold + AppBar(title: 'Playground')
  - ListView 列出 demo 项，当前只有一项：「Flutter 焦点 Demo」→ 路由 `/focus-demo`
  - 点击 demo 项 → Navigator.pushNamed 跳到对应路由
  - 入口项布局：ListTile(title + trailing arrow)
  - `flutter analyze` 无 error

---

## R003-HM002：lib/main.dart — 注册 named routes + home=HomePage `⬜`

- 文件：`flutter_logic/lib/main.dart`
- 改动类型：修改
- domain: ui
- task_layer: foundation
- depends_on: [R003-HM001]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `MaterialApp.home` 改为 `HomePage()`
  - `MaterialApp.routes` 注册 `/focus-demo` → `PersonalCenterDemoPage`
  - `MaterialApp.title` 改为 'Flutter Playground'（反映实验场语义）
  - `flutter analyze` 无 error

---

## R003-HM003：测试 + 回归验证 `⬜`

- 改动类型：测试
- domain: ui
- task_layer: foundation
- depends_on: [R003-HM001, R003-HM002]
- priority: 3
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - 新增 `test/home_page_test.dart`：
    - 启动后看到 'Playground' AppBar + 'Flutter 焦点 Demo' ListTile
    - 点击 ListTile → 跳到 PersonalCenterDemoPage（看到 '个人中心' AppBar）
    - PersonalCenterDemoPage AppBar 自带返回箭头（默认 back 行为）
  - 现有测试通过：`flutter test`（含 widget + 新增 home 测试）+ `flutter test integration_test/` 4 场景全绿
  - `flutter analyze` 无 error
