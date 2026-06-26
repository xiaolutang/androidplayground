import 'package:flutter/material.dart';
import 'pages/personal_center_page.dart';

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter 焦点 Demo',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const PersonalCenterDemoPage(),
    );
  }
}
