// 豆豆 App — 思维学科「纯新用户」课时页 (Figma node 650:22596, 375x836).
//
// 原生组件实现：文字用 Text、卡片用 Container、课时列表数据驱动、可点击。
// 仅图标/角色/插画等图形用栅格素材（无法用代码画）；颜色、布局、文字、
// 按钮全部原生。固定 375x836 画布按 Figma 坐标还原，FittedBox 缩放适配。

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

const String doudouStudyRoute = '/doudou-study';

const double kW = 375;
const double kH = 836;
const String _img = 'assets/doudouui/study/';

// 设计 token（来自 Figma 变量）。
class _C {
  const _C._();
  static const Color bg = Color(0xFFEBF9FF); // 学科-1 页面底
  static const Color cardLine = Color(0xFFF5F4F4); // 灰-2 卡片描边
  static const Color subjectLine = Color(0xFFDBF3FF); // 学科-2 选中描边
  static const Color subject4 = Color(0xFF33BBFF); // 学科-4 编号/强调 (#3BF)
  static const Color subject5 = Color(0xFF0090D9); // 学科-5 标题
  static const Color subject6 = Color(0xFF0C567A); // 学科-6 深蓝文字
  static const Color gray4 = Color(0xFFB2B2B2);
  static const Color gray5 = Color(0xFF666666);
  static const Color gray6 = Color(0xFF404040);
  static const Color green = Color(0xFF4AA12D); // 主绿（学习）
  static const Color greenExp = Color(0xFF5DC43B); // 体验气泡
}

// ---------------------------------------------------------------------------
// 页面。
// ---------------------------------------------------------------------------

class DoudouStudyPage extends StatefulWidget {
  const DoudouStudyPage({super.key});
  @override
  State<DoudouStudyPage> createState() => _DoudouStudyPageState();
}

class _DoudouStudyPageState extends State<DoudouStudyPage> {
  @override
  void initState() {
    super.initState();
    // 竖屏页面。
    SystemChrome.setPreferredOrientations(<DeviceOrientation>[
      DeviceOrientation.portraitUp,
    ]);
    SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.manual,
      overlays: const <SystemUiOverlay>[],
    );
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(DeviceOrientation.values);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData baseTheme = Theme.of(context);
    return Theme(
      data: baseTheme.copyWith(
        textTheme: baseTheme.textTheme.apply(fontFamily: 'AlibabaPuHuiTi'),
        primaryTextTheme:
            baseTheme.primaryTextTheme.apply(fontFamily: 'AlibabaPuHuiTi'),
      ),
      child: Scaffold(
        backgroundColor: _C.bg,
        body: Center(
          child: FittedBox(
            fit: BoxFit.contain,
            child: SizedBox(
              width: kW,
              height: kH,
              child: const _StudyCanvas(),
            ),
          ),
        ),
      ),
    );
  }
}

class _StudyCanvas extends StatelessWidget {
  const _StudyCanvas();

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: const <Widget>[
        Positioned(left: 0, top: 0, child: _SubjectArea()),
        Positioned(
            left: 0, top: 100, right: 0, bottom: 90, child: _LessonSheet()),
        Positioned(left: 20, top: 100, child: _Banner()),
        Positioned(left: 0, bottom: 0, child: _BottomTab()),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// 顶部：状态栏 + 科目 tab（思维 / 英语 / 美育）。
// ---------------------------------------------------------------------------

class _SubjectArea extends StatelessWidget {
  const _SubjectArea();
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: kW,
      height: 100,
      child: Column(
        children: const <Widget>[
          _StatusBar(),
          Expanded(child: _SubjectTabs()),
        ],
      ),
    );
  }
}

class _StatusBar extends StatelessWidget {
  const _StatusBar();
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 44,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 44),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: <Widget>[
            const Text(
              '9:41',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: Colors.black,
                letterSpacing: -0.28,
              ),
            ),
            Image.asset('${_img}status_signal.png',
                height: 11, fit: BoxFit.contain),
          ],
        ),
      ),
    );
  }
}

class _SubjectTabs extends StatelessWidget {
  const _SubjectTabs();
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 56,
      child: Stack(
        children: <Widget>[
          // 思维 IP（右上小装饰）
          Positioned(
              right: 0,
              top: 0,
              child: Image.asset('${_img}subject_ip.png',
                  width: 84, height: 84, fit: BoxFit.contain)),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Row(
              children: const <Widget>[
                _SubjectTab(label: '思维', selected: true),
                SizedBox(width: 14),
                _SubjectTab(label: '英语', selected: false),
                SizedBox(width: 14),
                _SubjectTabWithMeiyu(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SubjectTab extends StatelessWidget {
  const _SubjectTab({required this.label, required this.selected});
  final String label;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 62,
      height: 44,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          if (selected)
            Positioned(
                bottom: 7,
                child: Image.asset('${_img}subject_highlight.png',
                    width: 62, height: 18, fit: BoxFit.contain)),
          Text(
            label,
            style: TextStyle(
              fontSize: selected ? 24 : 20,
              fontWeight: FontWeight.w500,
              color: selected ? _C.gray6 : const Color(0x4D404040),
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }
}

/// 美育 tab（带「体验」气泡）。
class _SubjectTabWithMeiyu extends StatelessWidget {
  const _SubjectTabWithMeiyu();
  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        Container(
          width: 71,
          height: 32,
          margin: const EdgeInsets.only(top: 6),
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border.all(color: _C.cardLine),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              const Text('+', style: TextStyle(fontSize: 18, color: _C.gray6)),
              const SizedBox(width: 2),
              Text('美育',
                  style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w500,
                      color: const Color(0xB3404040))),
            ],
          ),
        ),
        Positioned(right: -2, top: -6, child: _ExperienceBadge()),
      ],
    );
  }
}

class _ExperienceBadge extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(
          color: _C.greenExp, borderRadius: BorderRadius.circular(999)),
      child: const Text('体验',
          style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: Colors.white,
              height: 1.5)),
    );
  }
}

// ---------------------------------------------------------------------------
// 课时白底面板（含 banner / 课前准备 / 标题 / 课程列表）。
// ---------------------------------------------------------------------------

class _LessonSheet extends StatelessWidget {
  const _LessonSheet();
  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 74, 20, 8), // 顶部留 banner 高度
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const _PrepRow(),
          const SizedBox(height: 12),
          const _SectionHeader(title: '1年级下册 图形计数', pending: 13),
          Expanded(child: _CourseList()),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 勇士升级赛 banner（浮在面板顶部）。
// ---------------------------------------------------------------------------

class _Banner extends StatelessWidget {
  const _Banner();
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 335,
      height: 74,
      child: Stack(
        children: <Widget>[
          Positioned(left: 0, top: 10, child: _BannerProgress()),
          const Positioned(right: 4, top: 4, child: _BannerTarget()),
        ],
      ),
    );
  }
}

/// 目标图：球 + 星星 + 角色（叠加在 60×60 内）。
class _BannerTarget extends StatelessWidget {
  const _BannerTarget();
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 60,
      height: 60,
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: <Widget>[
          Image.asset('${_img}banner_role.png',
              width: 60, height: 60, fit: BoxFit.contain),
          Image.asset('${_img}banner_ball.png',
              width: 60, height: 60, fit: BoxFit.contain),
          Positioned(
              left: -2,
              top: 3,
              child: Image.asset('${_img}banner_star.png',
                  width: 30, height: 30, fit: BoxFit.contain)),
        ],
      ),
    );
  }
}

class _BannerProgress extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 254,
      height: 31,
      child: Stack(
        children: <Widget>[
          const Positioned(
              top: 0,
              child: Text('勇士升级赛待开始 完课赢超萌装扮！',
                  style: TextStyle(fontSize: 14, color: Color(0xFF004161)))),
          Positioned(
            bottom: 0,
            left: 0,
            width: 250,
            height: 18,
            child: Stack(
              clipBehavior: Clip.none,
              children: <Widget>[
                Positioned(
                  left: 0,
                  bottom: 0,
                  child: Container(
                    width: 250,
                    height: 6,
                    decoration: BoxDecoration(
                        color: _C.cardLine,
                        borderRadius: BorderRadius.circular(3)),
                    child: FractionallySizedBox(
                      alignment: Alignment.centerLeft,
                      widthFactor: 0.4,
                      child: Container(
                          decoration: BoxDecoration(
                              color: _C.subject4,
                              borderRadius: BorderRadius.circular(3))),
                    ),
                  ),
                ),
                const Positioned(
                    right: 0, bottom: 2, child: _ProgressNode(value: '6')),
                const Positioned(
                    right: 145, bottom: 2, child: _ProgressNode(value: '3')),
                const Positioned(
                    right: 90, bottom: 2, child: _ProgressNode(value: '4')),
                const Positioned(
                    left: 34, bottom: 2, child: _ProgressNode(value: '2')),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ProgressNode extends StatelessWidget {
  const _ProgressNode({required this.value});
  final String value;
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 24,
      height: 24,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          Image.asset('${_img}progress_node.png',
              width: 24, height: 24, fit: BoxFit.contain),
          Text(value,
              style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF004161),
                  height: 1.0)),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 课前准备（4 个入口）。
// ---------------------------------------------------------------------------

class _PrepRow extends StatelessWidget {
  const _PrepRow();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 335,
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: _C.subjectLine),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(
        children: const <Widget>[
          _PrepItem(icon: '${_img}prep_advisor.png', label: '添加顾问'),
          _PrepItem(icon: '${_img}prep_remind.png', label: '设置提醒'),
          _PrepItem(icon: null, label: '阅读档案'),
          _PrepItem(icon: null, label: '学前测评'),
        ],
      ),
    );
  }
}

class _PrepItem extends StatelessWidget {
  const _PrepItem({required this.icon, required this.label});
  final String? icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: InkWell(
        onTap: () {},
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              SizedBox(
                width: 24,
                height: 24,
                child: icon == null
                    ? const SizedBox()
                    : Image.asset(icon!, fit: BoxFit.contain),
              ),
              const SizedBox(height: 4),
              Text(label,
                  style: const TextStyle(fontSize: 14, color: _C.subject6)),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 课时分组标题（待补 N + 箭头）。
// ---------------------------------------------------------------------------

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, required this.pending});
  final String title;
  final int pending;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 335,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: <Widget>[
          Text(title,
              style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                  color: _C.subject5)),
          InkWell(
            onTap: () {},
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text('待补 $pending',
                    style: const TextStyle(fontSize: 14, color: _C.gray5)),
                const SizedBox(width: 4),
                Image.asset('${_img}arrow.png',
                    width: 16, height: 16, fit: BoxFit.contain),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 课程列表（数据驱动）。
// ---------------------------------------------------------------------------

enum _CourseState { done, current, todo, locked }

class _Course {
  const _Course(
      {required this.no,
      required this.title,
      required this.state,
      this.date,
      this.icon});
  final int no;
  final String title;
  final _CourseState state;
  final String? date; // 锁定态显示的日期
  final String? icon; // 课程图标（默认 course_icon_base）
}

const List<_Course> _courses = <_Course>[
  _Course(no: 1, title: '看图列式-破十法', state: _CourseState.done),
  _Course(no: 2, title: '多次变化问题-求部分', state: _CourseState.todo),
  _Course(no: 3, title: '一样多问题-求差', state: _CourseState.current),
  _Course(no: 4, title: '一样多问题-求总数', state: _CourseState.todo),
  _Course(no: 5, title: '赶超问题', state: _CourseState.locked, date: '2.23'),
  _Course(
      no: 1,
      title: '周奖励',
      state: _CourseState.locked,
      date: '2.23',
      icon: 'weekly_icon'),
];

class _CourseList extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.only(top: 4),
      physics: const ClampingScrollPhysics(),
      itemCount: _courses.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (BuildContext _, int i) => _CourseCard(course: _courses[i]),
    );
  }
}

class _CourseCard extends StatelessWidget {
  const _CourseCard({required this.course});
  final _Course course;

  @override
  Widget build(BuildContext context) {
    if (course.state == _CourseState.current) {
      return _CurrentCard(course: course);
    }
    final bool dim = course.state == _CourseState.locked;
    final Color titleColor = dim ? _C.gray4 : _C.gray6;
    final String icon = course.icon ?? 'course_icon_base';
    return InkWell(
      onTap: () {},
      child: Container(
        width: 335,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 5),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: _C.cardLine),
          borderRadius: BorderRadius.circular(24),
        ),
        child: Row(
          children: <Widget>[
            SizedBox(
              width: 30,
              child: Text('${course.no}.',
                  style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: _C.subject4,
                      height: 1.5)),
            ),
            Image.asset('$_img$icon.png',
                width: 32, height: 32, fit: BoxFit.contain),
            const SizedBox(width: 8),
            Expanded(
                child: Text(course.title,
                    style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w500,
                        color: titleColor,
                        height: 1.5))),
            _CourseStateMark(course: course),
          ],
        ),
      ),
    );
  }
}

/// 课程状态标记（右侧图标）。
class _CourseStateMark extends StatelessWidget {
  const _CourseStateMark({required this.course});
  final _Course course;

  @override
  Widget build(BuildContext context) {
    switch (course.state) {
      case _CourseState.done:
        return Image.asset('${_img}stamp.png',
            width: 28, height: 28, fit: BoxFit.contain);
      case _CourseState.todo:
        return Container(
          width: 28,
          height: 28,
          alignment: Alignment.center,
          child: Container(
            width: 18,
            height: 18,
            decoration:
                const BoxDecoration(color: _C.subject4, shape: BoxShape.circle),
            alignment: Alignment.center,
            child: const Text('补',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 11,
                    fontWeight: FontWeight.bold)),
          ),
        );
      case _CourseState.locked:
        return SizedBox(
          width: 28,
          height: 28,
          child: Stack(
            alignment: Alignment.center,
            children: <Widget>[
              Image.asset('${_img}lock.png',
                  width: 24, height: 24, fit: BoxFit.contain),
              if (course.date != null)
                Positioned(
                  bottom: -2,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(15)),
                    child: Text(course.date!,
                        style: const TextStyle(fontSize: 10, color: _C.gray4)),
                  ),
                ),
            ],
          ),
        );
      case _CourseState.current:
        return const SizedBox(); // current 卡片另渲染
    }
  }
}

/// 当前进行中的课时卡（蓝底 + 封面 + 开始学习按钮）。
class _CurrentCard extends StatelessWidget {
  const _CurrentCard({required this.course});
  final _Course course;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 335,
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
      decoration: BoxDecoration(
        color: _C.bg,
        border: Border.all(color: _C.subject4, width: 3),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            children: <Widget>[
              SizedBox(
                  width: 30,
                  child: Text('${course.no}.',
                      style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: _C.subject4,
                          height: 1.5))),
              SizedBox(
                width: 50,
                height: 50,
                child: Stack(
                  alignment: Alignment.center,
                  children: <Widget>[
                    Image.asset('${_img}current_bg.png',
                        width: 50, height: 50, fit: BoxFit.contain),
                    Image.asset('${_img}current_cover.png',
                        width: 45, height: 45, fit: BoxFit.contain),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                  child: Text(course.title,
                      style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w500,
                          color: _C.subject6,
                          height: 1.5))),
            ],
          ),
          const SizedBox(height: 16),
          InkWell(
            onTap: () {},
            child: Container(
              height: 44,
              decoration: BoxDecoration(
                  color: _C.subject4, borderRadius: BorderRadius.circular(30)),
              alignment: Alignment.center,
              child: const Text('开始学习',
                  style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w500,
                      color: Colors.white)),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 底部 tab bar（学习/任务/广场/伴读/我的）。
// ---------------------------------------------------------------------------

class _BottomTab extends StatelessWidget {
  const _BottomTab();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: kW,
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: _C.cardLine)),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          SizedBox(
            height: 56,
            child: Row(
              children: const <Widget>[
                _TabItem(
                    icon: '${_img}tab_learn.png', label: '学习', color: _C.green),
                _TabItem(
                    icon: '${_img}tab_task.png', label: '任务', color: _C.gray4),
                _TabItem(
                    icon: '${_img}tab_square.png',
                    label: '广场',
                    color: _C.gray4),
                _TabItem(
                    icon: '${_img}tab_read.png', label: '伴读', color: _C.gray4),
                _TabItem(
                    icon: '${_img}tab_mine.png', label: '我的', color: _C.gray4),
              ],
            ),
          ),
          // iOS home indicator
          Container(
            height: 34,
            alignment: Alignment.bottomCenter,
            padding: const EdgeInsets.only(bottom: 8),
            child: Container(
                width: 134,
                height: 5,
                decoration: BoxDecoration(
                    color: Colors.black,
                    borderRadius: BorderRadius.circular(100))),
          ),
        ],
      ),
    );
  }
}

class _TabItem extends StatelessWidget {
  const _TabItem(
      {required this.icon, required this.label, required this.color});
  final String icon;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: InkWell(
        onTap: () {},
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Image.asset(icon, width: 40, height: 40, fit: BoxFit.contain),
            const SizedBox(height: 2),
            Text(label,
                style: TextStyle(fontSize: 12, color: color, height: 1.0)),
          ],
        ),
      ),
    );
  }
}
