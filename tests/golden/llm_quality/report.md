# LLM Patch 命中率报告 **[mock]**

> 生成时间: 2026-06-22 02:18:45
> 样本数: 20（标注集共 20 样本）
> 模式: mock（无 API key，演示方法）

## 命中率汇总

| 指标 | 值 | 阈值 | 状态 |
|------|----|------|------|
| Schema 合规率 | 100.0% (20/20) | >=95% | PASS |
| 关键字段命中率 | 100.0% (20/20) | >=80% | PASS |

> MVP 阶段：方法可执行 + 报告产出即 pass，数值仅供参考。

## 按 prompt_type 分组

| prompt_type | N | Schema 合规 | 关键字段命中 |
|-------------|---|-------------|-------------|
| fix_patch | 15 | 15/15 (100%) | 15/15 (100%) |
| reflection | 5 | 5/5 (100%) | 5/5 (100%) |

## 样本明细

| sample_id | prompt_type | schema_ok | key_fields_ok | latency_ms | error |
|-----------|-------------|-----------|---------------|------------|-------|
| blank_screen_01 | fix_patch | YES | YES | 1 |  |
| blank_screen_02 | fix_patch | YES | YES | 1 |  |
| blank_screen_03 | fix_patch | YES | YES | 1 |  |
| blank_screen_04 | fix_patch | YES | YES | 1 |  |
| blank_screen_05 | fix_patch | YES | YES | 1 |  |
| crash_npe_01 | fix_patch | YES | YES | 1 |  |
| crash_npe_02 | fix_patch | YES | YES | 1 |  |
| crash_npe_03 | fix_patch | YES | YES | 1 |  |
| crash_npe_04 | fix_patch | YES | YES | 1 |  |
| crash_npe_05 | fix_patch | YES | YES | 1 |  |
| loading_stuck_01 | fix_patch | YES | YES | 1 |  |
| loading_stuck_02 | fix_patch | YES | YES | 1 |  |
| loading_stuck_03 | fix_patch | YES | YES | 1 |  |
| loading_stuck_04 | fix_patch | YES | YES | 1 |  |
| loading_stuck_05 | fix_patch | YES | YES | 1 |  |
| reflection_01 | reflection | YES | YES | 1 |  |
| reflection_02 | reflection | YES | YES | 1 |  |
| reflection_03 | reflection | YES | YES | 1 |  |
| reflection_04 | reflection | YES | YES | 1 |  |
| reflection_05 | reflection | YES | YES | 1 |  |

## 结论

- 本报告使用 **mock** 模式生成（无 NEW_API_API_KEY）。
- 方法已验证可执行：样本加载 -> LLM 调用 -> schema/字段校验 -> 报告产出。
- 配置 API key 后重新运行即可获得真实 LLM 基线数据。
