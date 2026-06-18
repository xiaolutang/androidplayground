"""校验 design 3.1 项目结构目录树存在性。

依据: .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 第 65-170 行。
本任务（R001-INF01）只覆盖 agent/ 子树；frontend/、docker-compose.yml、Dockerfile、Makefile
属于后续前端/部署任务，不在 INF01 验收范围（见 INF01.2 目录空骨架定义）。
"""
from pathlib import Path

# 仓库根目录 = tests/ 的上两级
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT = REPO_ROOT / "agent"

# design 3.1 中 agent/ 子树下的全部路径（相对 agent/）
# 包含目录与文件，统一校验 exists()
EXPECTED_PATHS = [
    # intake
    "intake/__init__.py",
    "intake/bug_report_adapter.py",
    "intake/adapters/__init__.py",
    "intake/adapters/bugly_adapter.py",
    "intake/adapters/sentry_adapter.py",
    # reproduce
    "reproduce/__init__.py",
    "reproduce/emulator_pool.py",
    "reproduce/apk_installer.py",
    "reproduce/adb_tools.py",
    "reproduce/reproduce_runner.py",
    "reproduce/screenshot_collector.py",
    # vision
    "vision/__init__.py",
    "vision/vision_decision_engine.py",
    # signal
    "signal/__init__.py",
    "signal/logcat_listener.py",
    "signal/flutter_error_listener.py",
    "signal/process_listener.py",
    "signal/visual_signal_detector.py",
    # kb
    "kb/__init__.py",
    "kb/stores/__init__.py",
    "kb/stores/trajectory_store.py",
    "kb/stores/negative_knowledge_store.py",
    "kb/stores/pattern_store.py",
    "kb/retriever.py",
    "kb/staleness_checker.py",
    # playbook
    "playbook/__init__.py",
    "playbook/registry.py",
    "playbook/schema.py",
    "playbook/definitions/__init__.py",
    "playbook/definitions/crash_playbook.py",
    "playbook/definitions/blank_playbook.py",
    "playbook/definitions/loading_playbook.py",
    "playbook/definitions/no_response_playbook.py",
    "playbook/definitions/data_error_playbook.py",
    # anchor
    "anchor/__init__.py",
    "anchor/anchor_library.py",
    # gap
    "gap/__init__.py",
    "gap/gap_store.py",
    "gap/unlock_value_scorer.py",
    # assessment
    "assessment/__init__.py",
    "assessment/info_sufficiency_evaluator.py",
    "assessment/symptom_classifier.py",
    "assessment/confidence_evaluator.py",
    # diagnosis
    "diagnosis/__init__.py",
    "diagnosis/playbook_executor.py",
    "diagnosis/hypothesis_engine.py",
    "diagnosis/root_cause_locator.py",
    # fix
    "fix/__init__.py",
    "fix/auto_fixer.py",
    "fix/regression_verifier.py",
    "fix/pr_submitter.py",
    # gap_mgmt
    "gap_mgmt/__init__.py",
    "gap_mgmt/gap_diagnoser.py",
    "gap_mgmt/reflow_manager.py",
    "gap_mgmt/manual_fix_recorder.py",
    # report
    "report/__init__.py",
    "report/diagnosis_report_generator.py",
    # reflection
    "reflection/__init__.py",
    "reflection/reflection_agent.py",
    # api
    "api/__init__.py",
    "api/routers/__init__.py",
    "api/routers/report_router.py",
    "api/routers/gap_router.py",
    "api/dtos/__init__.py",
    # schemas
    "schemas/__init__.py",
    "schemas/bug_report.py",
    "schemas/playbook.py",
    "schemas/trajectory.py",
    "schemas/confidence.py",
    "schemas/fix_patch.py",
    "schemas/capability_gap.py",
    "schemas/kb_entry.py",
    "schemas/metric_point.py",
    # infra
    "infra/__init__.py",
    "infra/llm_gateway.py",
    "infra/adb_client.py",
    "infra/git_client.py",
    "infra/db.py",
    "infra/config.py",
    # 顶层
    "__init__.py",
    "orchestrator.py",
    "main.py",
    "pyproject.toml",
]


def test_design_3_1_agent_subtree_exists():
    """遍历 design 3.1 列出的全部 agent/ 路径，断言每个存在。"""
    missing = []
    for rel in EXPECTED_PATHS:
        p = AGENT / rel
        if not p.exists():
            missing.append(rel)
    assert not missing, f"缺失以下路径（相对 agent/）: {missing}"


def test_tests_dirs_exist():
    """INF01.2 要求的 tests 子目录。"""
    tests = REPO_ROOT / "tests"
    for sub in ["unit", "integration", "state_machine", "integration_bf002", "golden", "fixtures", "e2e"]:
        d = tests / sub
        assert d.is_dir(), f"tests/{sub}/ 不存在"
        assert (d / "__init__.py").exists(), f"tests/{sub}/__init__.py 不存在"
