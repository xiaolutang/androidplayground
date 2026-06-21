"""Golden set 测试（R001-INT04 AC-5）。

所有测试标记 ``@pytest.mark.golden``，需 ``--run-golden`` 显式触发。

这些测试验证三类报告脚本的产出（非数值达标，MVP 看方法可执行性）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[1]


@pytest.mark.golden
class TestLLMQualityReport:
    """AC-1: LLM patch 命中率报告。"""

    def test_run_llm_quality_produces_report(self) -> None:
        """run_llm_quality.py 可执行并产出 report.md。"""
        script = _THIS_DIR / "llm_quality" / "run_llm_quality.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_REPO_ROOT),
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        report = _THIS_DIR / "llm_quality" / "report.md"
        assert report.exists(), "report.md not produced"
        content = report.read_text(encoding="utf-8")
        assert "命中率" in content or "Schema" in content

    def test_llm_quality_report_has_samples(self) -> None:
        """report.md 包含样本明细。"""
        report = _THIS_DIR / "llm_quality" / "report.md"
        if not report.exists():
            pytest.skip("report.md not generated yet")
        content = report.read_text(encoding="utf-8")
        assert "sample_id" in content or "blank_screen" in content


@pytest.mark.golden
class TestConfidenceCalibration:
    """AC-2: 置信度校准报告。"""

    def test_run_calibration_produces_report(self) -> None:
        """run_calibration.py 可执行并产出 calibration_report.md。"""
        script = _THIS_DIR / "confidence" / "run_calibration.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_REPO_ROOT),
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        report = _THIS_DIR / "confidence" / "calibration_report.md"
        assert report.exists(), "calibration_report.md not produced"
        content = report.read_text(encoding="utf-8")
        assert "Brier" in content

    def test_calibration_has_reliability_diagram(self) -> None:
        """calibration_report.md 包含 reliability diagram。"""
        report = _THIS_DIR / "confidence" / "calibration_report.md"
        if not report.exists():
            pytest.skip("calibration_report.md not generated yet")
        content = report.read_text(encoding="utf-8")
        assert "Reliability" in content or "reliability" in content


@pytest.mark.golden
class TestVisionReport:
    """AC-3: 视觉决策 golden 报告。"""

    def test_run_vision_produces_report(self) -> None:
        """run_vision.py 可执行并产出 report.md。"""
        script = _THIS_DIR / "vision" / "run_vision.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_REPO_ROOT),
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        report = _THIS_DIR / "vision" / "report.md"
        assert report.exists(), "report.md not produced"
        content = report.read_text(encoding="utf-8")
        assert "准确率" in content or "Accuracy" in content

    def test_vision_report_has_confusion_matrix(self) -> None:
        """vision report.md 包含混淆矩阵。"""
        report = _THIS_DIR / "vision" / "report.md"
        if not report.exists():
            pytest.skip("report.md not generated yet")
        content = report.read_text(encoding="utf-8")
        assert "混淆矩阵" in content or "Confusion" in content

    def test_vision_cold_start_accuracy(self) -> None:
        """冷启动准确率 >= 50%（AC-3 threshold）。"""
        report = _THIS_DIR / "vision" / "report.md"
        if not report.exists():
            pytest.skip("report.md not generated yet")
        content = report.read_text(encoding="utf-8")
        # 查找准确率百分比
        import re

        match = re.search(r"(\d+\.?\d*)%", content)
        if match:
            accuracy = float(match.group(1))
            assert accuracy >= 50.0, f"Cold start accuracy {accuracy}% < 50%"
