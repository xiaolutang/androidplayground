"""BF002 模拟器独立集成测试包（R001-INT03）。

手动集成测试，需 ``--run-emulator`` 显式触发，不进主 CI。

覆盖场景：
- 真实模拟器启停
- ADB 动作（install / uninstall / screenshot / shell）
- 截图验证
- 超时重试
- 故障注入表 BF002 场景（模拟器不可用 / ADB offline / 超时）
"""
