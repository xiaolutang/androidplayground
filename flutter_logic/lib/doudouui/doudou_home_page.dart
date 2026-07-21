import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

const String doudouHomeRoute = '/doudou-home';

class DoudouHomePage extends StatefulWidget {
  const DoudouHomePage({super.key});

  @override
  State<DoudouHomePage> createState() => _DoudouHomePageState();
}

class _DoudouHomePageState extends State<DoudouHomePage> {
  @override
  void initState() {
    super.initState();
    SystemChrome.setPreferredOrientations(const <DeviceOrientation>[
      DeviceOrientation.portraitUp,
    ]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(DeviceOrientation.values);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        top: false,
        bottom: false,
        child: DoudouHomeScaledCanvas(),
      ),
    );
  }
}

@visibleForTesting
class DoudouHomeScaledCanvas extends StatelessWidget {
  const DoudouHomeScaledCanvas({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double scale = constraints.maxWidth / DoudouHomeCanvas.width;
        return SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          child: SizedBox(
            width: constraints.maxWidth,
            height: DoudouHomeCanvas.height * scale,
            child: Transform.scale(
              alignment: Alignment.topLeft,
              scale: scale,
              child: const DoudouHomeCanvas(),
            ),
          ),
        );
      },
    );
  }
}

@visibleForTesting
class DoudouHomeCanvas extends StatelessWidget {
  const DoudouHomeCanvas({super.key});

  static const double width = 375;
  static const double height = 1363;
  static const String assetRoot = 'assets/doudouui/';

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: const SizedBox(
        width: width,
        height: height,
        child: ColoredBox(
          color: Colors.white,
          child: Stack(
            clipBehavior: Clip.hardEdge,
            children: <Widget>[
              _HeaderBackground(),
              _FakeStatusBar(),
              _TitleBar(),
              _SectionHeader(top: 110, title: '模块名称', showMore: true),
              _ExactImage(
                left: 20,
                top: 143,
                width: 335,
                height: 200,
                radius: 24,
                asset: 'hero_banner_exact.png',
              ),
              _ExactImage(
                left: 20,
                top: 359,
                width: 164,
                height: 163,
                radius: 10,
                asset: 'card_01.png',
              ),
              _ExactImage(
                left: 191,
                top: 359,
                width: 164,
                height: 163,
                radius: 10,
                asset: 'card_02.png',
              ),
              _ExactImage(
                left: 20,
                top: 534,
                width: 106,
                height: 106,
                radius: 8,
                asset: 'card_03.png',
              ),
              _ExactImage(
                left: 135,
                top: 534,
                width: 106,
                height: 106,
                radius: 8,
                asset: 'card_01.png',
              ),
              _ExactImage(
                left: 249,
                top: 534,
                width: 106,
                height: 106,
                radius: 8,
                asset: 'card_02.png',
              ),
              _SectionHeader(top: 673, title: '一行2个'),
              _TwoColumnResources(),
              _SectionHeader(top: 947, title: '一行3个'),
              _ThreeColumnResources(),
              _HomeIndicator(),
            ],
          ),
        ),
      ),
    );
  }
}

class _HeaderBackground extends StatelessWidget {
  const _HeaderBackground();

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: 0,
      top: 0,
      width: 375,
      height: 88,
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              const Color(0xFFD2F7C6).withValues(alpha: 0.95),
              Colors.white,
            ],
          ),
        ),
      ),
    );
  }
}

class _FakeStatusBar extends StatelessWidget {
  const _FakeStatusBar();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: <Widget>[
        const Positioned(
          left: 44,
          top: 16,
          child: Text(
            '9:41',
            style: TextStyle(
              color: Colors.black,
              fontSize: 14,
              height: 1.2,
              fontWeight: FontWeight.w500,
              letterSpacing: -0.28,
            ),
          ),
        ),
        Positioned(
          left: 264,
          top: 17,
          width: 66.6,
          height: 11.333,
          child: Image.asset(
            '${DoudouHomeCanvas.assetRoot}status_icons.png',
            fit: BoxFit.fill,
            filterQuality: FilterQuality.low,
          ),
        ),
      ],
    );
  }
}

class _TitleBar extends StatelessWidget {
  const _TitleBar();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: <Widget>[
        const Positioned(
          left: 20,
          top: 52,
          child: Text(
            '绿豆豆乐园',
            style: TextStyle(
              color: Color(0xFF155200),
              fontSize: 24,
              height: 1.5,
              fontWeight: FontWeight.w500,
              letterSpacing: 0,
            ),
          ),
        ),
        Positioned(
          left: 276,
          top: 61,
          width: 16,
          height: 16,
          child: Image.asset(
            '${DoudouHomeCanvas.assetRoot}info_icon.png',
            fit: BoxFit.fill,
            filterQuality: FilterQuality.low,
          ),
        ),
        const Positioned(
          left: 296,
          top: 58,
          child: Text(
            '更多信息',
            style: TextStyle(
              color: Color(0xFF709763),
              fontSize: 14,
              height: 1.5,
              fontWeight: FontWeight.w400,
              letterSpacing: 0,
            ),
          ),
        ),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final double top;
  final String title;
  final bool showMore;

  const _SectionHeader({
    required this.top,
    required this.title,
    this.showMore = false,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: 20,
      top: top,
      width: 335,
      height: 34,
      child: Row(
        children: <Widget>[
          Image.asset(
            '${DoudouHomeCanvas.assetRoot}section_book_icon_exact.png',
            width: 28,
            height: 28,
            filterQuality: FilterQuality.low,
          ),
          const SizedBox(width: 4),
          Text(
            title,
            style: const TextStyle(
              color: Color(0xFF4AA12D),
              fontSize: 18,
              height: 1.5,
              fontWeight: FontWeight.w500,
              letterSpacing: 0,
            ),
          ),
          const Spacer(),
          if (showMore) const _MoreButton(),
        ],
      ),
    );
  }
}

class _MoreButton extends StatelessWidget {
  const _MoreButton();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 26,
      padding: const EdgeInsets.only(left: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(999),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: Color(0x10000000),
            blurRadius: 2,
            offset: Offset(0, 1),
          ),
        ],
      ),
      child: Row(
        children: <Widget>[
          const Text(
            '更多',
            style: TextStyle(
              color: Color(0xFF4AA12D),
              fontSize: 14,
              height: 1,
              fontWeight: FontWeight.w400,
            ),
          ),
          Image.asset(
            '${DoudouHomeCanvas.assetRoot}chevron_green.png',
            width: 20,
            height: 20,
            filterQuality: FilterQuality.low,
          ),
        ],
      ),
    );
  }
}

class _ExactImage extends StatelessWidget {
  final double left;
  final double top;
  final double width;
  final double height;
  final double radius;
  final String asset;

  const _ExactImage({
    required this.left,
    required this.top,
    required this.width,
    required this.height,
    required this.radius,
    required this.asset,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      width: width,
      height: height,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(radius),
        child: Image.asset(
          '${DoudouHomeCanvas.assetRoot}$asset',
          fit: BoxFit.cover,
          filterQuality: FilterQuality.low,
        ),
      ),
    );
  }
}

class _TwoColumnResources extends StatelessWidget {
  const _TwoColumnResources();

  @override
  Widget build(BuildContext context) {
    return const Stack(
      children: <Widget>[
        _ResourceTile(
          left: 20,
          top: 703,
          size: 164,
          cover: 'resource_cover_base.png',
          title: '古诗故事2则',
          tags: <String>['认知'],
          showTopRightFree: true,
        ),
        _ResourceTile(
          left: 191,
          top: 703,
          size: 164,
          cover: 'resource_cover_base.png',
          title: '古诗故事2则',
          tags: <String>['寓言故事', '认知'],
          bottomBadge: _CoverBadge.update,
        ),
      ],
    );
  }
}

class _ThreeColumnResources extends StatelessWidget {
  const _ThreeColumnResources();

  @override
  Widget build(BuildContext context) {
    return const Stack(
      children: <Widget>[
        _SmallResourceTile(
          left: 20,
          top: 980,
          cover: 'resource_01.png',
          title: '毛毛镇冰雪加油队',
          tags: <String>['寓言故事'],
          bottomBadge: _CoverBadge.subscribe,
        ),
        _SmallResourceTile(
          left: 135,
          top: 980,
          cover: 'resource_02.png',
          title: '多多罗财商启蒙',
          tags: <String>['认知'],
          showTopRightFree: true,
        ),
        _SmallResourceTile(
          left: 249,
          top: 980,
          cover: 'resource_03_base.png',
          coverOverlay: 'resource_03_overlay.png',
          title: '一二三四五六七',
          tags: <String>['寓言故事'],
          bottomBadge: _CoverBadge.subscribe,
        ),
        _SmallResourceTile(
          left: 20,
          top: 1147,
          cover: 'resource_01.png',
          title: '毛毛镇冰雪加油队',
          tags: <String>['寓言故事'],
          bottomBadge: _CoverBadge.subscribe,
        ),
        _SmallResourceTile(
          left: 135,
          top: 1147,
          cover: 'resource_02.png',
          title: '多多罗财商启蒙',
          tags: <String>['认知'],
          showTopRightFree: true,
        ),
        _SmallResourceTile(
          left: 249,
          top: 1147,
          cover: 'resource_03_base.png',
          coverOverlay: 'resource_03_overlay.png',
          title: '一二三四五六七',
          tags: <String>['寓言故事'],
          bottomBadge: _CoverBadge.subscribe,
          locked: true,
        ),
      ],
    );
  }
}

class _ResourceTile extends StatelessWidget {
  final double left;
  final double top;
  final double size;
  final String cover;
  final String? coverOverlay;
  final String title;
  final List<String> tags;
  final _CoverBadge? bottomBadge;
  final bool showTopRightFree;
  final bool locked;

  const _ResourceTile({
    required this.left,
    required this.top,
    required this.size,
    required this.cover,
    this.coverOverlay,
    required this.title,
    required this.tags,
    this.bottomBadge,
    this.showTopRightFree = false,
    this.locked = false,
  });

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      width: size,
      height: 224,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _CoverBox(
            size: size,
            cover: cover,
            coverOverlay: coverOverlay,
            bottomBadge: bottomBadge,
            showTopRightFree: showTopRightFree,
            locked: locked,
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Color(0xFF666666),
                fontSize: 16,
                height: 1.5,
                fontWeight: FontWeight.w400,
              ),
            ),
          ),
          const SizedBox(height: 2),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: _Tags(tags: tags),
          ),
        ],
      ),
    );
  }
}

class _SmallResourceTile extends StatelessWidget {
  final double left;
  final double top;
  final String cover;
  final String? coverOverlay;
  final String title;
  final List<String> tags;
  final _CoverBadge? bottomBadge;
  final bool showTopRightFree;
  final bool locked;

  const _SmallResourceTile({
    required this.left,
    required this.top,
    required this.cover,
    this.coverOverlay,
    required this.title,
    required this.tags,
    this.bottomBadge,
    this.showTopRightFree = false,
    this.locked = false,
  });

  @override
  Widget build(BuildContext context) {
    return _ResourceTile(
      left: left,
      top: top,
      size: 106,
      cover: cover,
      coverOverlay: coverOverlay,
      title: title,
      tags: tags,
      bottomBadge: bottomBadge,
      showTopRightFree: showTopRightFree,
      locked: locked,
    );
  }
}

enum _CoverBadge { subscribe, update }

class _CoverBox extends StatelessWidget {
  final double size;
  final String cover;
  final String? coverOverlay;
  final _CoverBadge? bottomBadge;
  final bool showTopRightFree;
  final bool locked;

  const _CoverBox({
    required this.size,
    required this.cover,
    this.coverOverlay,
    this.bottomBadge,
    this.showTopRightFree = false,
    this.locked = false,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: SizedBox(
        width: size,
        height: size,
        child: Stack(
          children: <Widget>[
            Positioned.fill(
              child: Image.asset(
                '${DoudouHomeCanvas.assetRoot}$cover',
                fit: BoxFit.cover,
                filterQuality: FilterQuality.low,
              ),
            ),
            if (coverOverlay != null)
              Positioned.fill(
                child: Image.asset(
                  '${DoudouHomeCanvas.assetRoot}$coverOverlay',
                  fit: BoxFit.cover,
                  filterQuality: FilterQuality.low,
                ),
              ),
            const Positioned(
              right: 6,
              bottom: 6,
              width: 16,
              height: 16,
              child: Image(
                image:
                    AssetImage('${DoudouHomeCanvas.assetRoot}icon_video.png'),
                fit: BoxFit.fill,
                filterQuality: FilterQuality.low,
              ),
            ),
            if (showTopRightFree)
              Positioned(
                right: 0,
                top: 0,
                width: size >= 160 ? 40 : 32,
                height: size >= 160 ? 20 : 16,
                child: _FreeBadge(isLarge: size >= 160),
              ),
            if (locked)
              Positioned.fill(
                child: ColoredBox(
                  color: const Color(0x4D222222),
                  child: Align(
                    alignment: Alignment.bottomRight,
                    child: Image.asset(
                      '${DoudouHomeCanvas.assetRoot}icon_lock.png',
                      width: 44,
                      height: 44,
                      filterQuality: FilterQuality.low,
                    ),
                  ),
                ),
              ),
            if (bottomBadge != null)
              Positioned(
                left: 6,
                bottom: 6,
                child: _BottomBadge(type: bottomBadge!),
              ),
          ],
        ),
      ),
    );
  }
}

class _FreeBadge extends StatelessWidget {
  final bool isLarge;

  const _FreeBadge({required this.isLarge});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: Color(0xFF40A12D),
        border: Border(
          left: BorderSide(color: Colors.white, width: 0.5),
          bottom: BorderSide(color: Colors.white, width: 0.5),
        ),
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(8),
        ),
      ),
      child: Center(
        child: Text(
          '限免',
          style: TextStyle(
            color: Colors.white,
            fontSize: isLarge ? 13 : 10,
            height: 1,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class _BottomBadge extends StatelessWidget {
  final _CoverBadge type;

  const _BottomBadge({required this.type});

  @override
  Widget build(BuildContext context) {
    final bool isUpdate = type == _CoverBadge.update;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: isUpdate ? const Color(0xCC40A12D) : const Color(0xCCFF9045),
        borderRadius: BorderRadius.circular(6),
      ),
      child: SizedBox(
        width: 30,
        height: 16,
        child: Center(
          child: Text(
            isUpdate ? '更新' : '订阅',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 10,
              height: 1,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ),
    );
  }
}

class _Tags extends StatelessWidget {
  final List<String> tags;

  const _Tags({required this.tags});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (int i = 0; i < tags.length; i++) ...<Widget>[
          if (i > 0) const SizedBox(width: 6),
          Container(
            height: 20,
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(
              color: const Color(0xFFEFF2F4),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              tags[i],
              style: const TextStyle(
                color: Color(0xFFB2B2B2),
                fontSize: 12,
                height: 1.5,
                fontWeight: FontWeight.w400,
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _HomeIndicator extends StatelessWidget {
  const _HomeIndicator();

  @override
  Widget build(BuildContext context) {
    return const Positioned(
      left: 0,
      bottom: 0,
      width: 375,
      height: 34,
      child: ColoredBox(
        color: Colors.white,
        child: Center(
          child: SizedBox(
            width: 134,
            height: 5,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.all(Radius.circular(100)),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
