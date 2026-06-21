#!/usr/bin/env python3
"""视觉决策 golden 报告脚本（R001-INT04 AC-3）。

PIL 生成截图样本 -> 像素方差检测（冷启动）-> vs 人工标注 ->
混淆矩阵 + 准确率 -> 生成 report.md。

Usage:
    cd agent && python3 tests/golden/vision/run_vision.py

冷启动测试（D11）：
- 锚点库空时，用纯像素方差检测（不依赖 BF003 VisualDecisionEngine 的 LLM 调用，
  因为无 API key 时 LLM 会降级 fallback）。
- 检测逻辑：白屏（方差≈0 + 均值>240）、黑屏（方差≈0 + 均值<15）、
  加载中（方差中等 + 特定模式）、正常（方差高）、异常（方差极低或极高）。

MVP 降级：
- 无 API key 时不调 LLM，纯像素分析（标注"像素方差检测"）。
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# -----------------------------------------------------------------------------
# 路径修正
# -----------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
# tests/golden/vision/run_vision.py -> parents[3]=repo root
_AGENT_ROOT = _THIS_DIR.parents[3]
sys.path.insert(0, str(_AGENT_ROOT))

SAMPLES_DIR = _THIS_DIR / "samples"
REPORT_PATH = _THIS_DIR / "report.md"

# 图片尺寸
IMG_W, IMG_H = 360, 640


# -----------------------------------------------------------------------------
# PIL 截图生成
# -----------------------------------------------------------------------------
def _generate_white_screen(name: str) -> Path:
    """生成白屏截图。"""
    img = Image.new("RGB", (IMG_W, IMG_H), (255, 255, 255))
    path = SAMPLES_DIR / name
    img.save(path)
    return path


def _generate_black_screen(name: str) -> Path:
    """生成黑屏截图。"""
    img = Image.new("RGB", (IMG_W, IMG_H), (0, 0, 0))
    path = SAMPLES_DIR / name
    img.save(path)
    return path


def _generate_loading_screen(name: str) -> Path:
    """生成加载中截图（简单 loading 动画）。"""
    img = Image.new("RGB", (IMG_W, IMG_H), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    # 中央 loading 圆环
    cx, cy = IMG_W // 2, IMG_H // 2
    r = 40
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=(100, 100, 100),
        width=5,
    )
    # 文字区域
    draw.text((cx - 30, cy + r + 20), "Loading...", fill=(80, 80, 80))
    path = SAMPLES_DIR / name
    img.save(path)
    return path


def _generate_normal_screen(name: str, seed: int = 0) -> Path:
    """生成正常 App 页面截图（有 UI 元素 + 内容）。"""
    random.seed(seed)
    img = Image.new("RGB", (IMG_W, IMG_H), (245, 245, 245))
    draw = ImageDraw.Draw(img)

    # 顶部导航栏
    draw.rectangle([0, 0, IMG_W, 60], fill=(60, 120, 200))
    draw.text((20, 20), "Home Page", fill=(255, 255, 255))

    # 内容卡片
    for i in range(4):
        y = 80 + i * 120
        draw.rectangle([10, y, IMG_W - 10, y + 100], fill=(255, 255, 255))
        draw.text((20, y + 10), f"Item {i+1}", fill=(50, 50, 50))
        draw.text((20, y + 40), f"Description text {i+1}", fill=(120, 120, 120))

    # 底部 tab 栏
    draw.rectangle([0, IMG_H - 50, IMG_W, IMG_H], fill=(250, 250, 250))
    for i in range(4):
        x = 45 + i * 90
        draw.ellipse([x, IMG_H - 40, x + 20, IMG_H - 20], fill=(200, 200, 200))

    path = SAMPLES_DIR / name
    img.save(path)
    return path


def _generate_abnormal_screen(name: str, seed: int = 0) -> Path:
    """生成异常截图（UI 错乱/乱码）。"""
    random.seed(seed)
    img = Image.new("RGB", (IMG_W, IMG_H), (255, 200, 200))
    draw = ImageDraw.Draw(img)
    # 错乱的 UI 元素
    for _ in range(20):
        x1 = random.randint(0, IMG_W - 50)
        y1 = random.randint(0, IMG_H - 50)
        x2 = x1 + random.randint(10, 80)
        y2 = y1 + random.randint(10, 80)
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        draw.rectangle([x1, y1, x2, y2], fill=color)
    # 噪声
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    path = SAMPLES_DIR / name
    img.save(path)
    return path


def generate_all_samples() -> list[tuple[Path, str]]:
    """生成全部截图样本，返回 [(path, ground_truth_label)]。"""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    samples: list[tuple[Path, str]] = []

    # 白屏 x2
    for i in range(2):
        p = _generate_white_screen(f"white_{i+1:02d}.png")
        samples.append((p, "blank_white"))

    # 黑屏 x2
    for i in range(2):
        p = _generate_black_screen(f"black_{i+1:02d}.png")
        samples.append((p, "blank_black"))

    # 加载中 x2
    for i in range(2):
        p = _generate_loading_screen(f"loading_{i+1:02d}.png")
        samples.append((p, "loading"))

    # 正常 x3
    for i in range(3):
        p = _generate_normal_screen(f"normal_{i+1:02d}.png", seed=i)
        samples.append((p, "normal"))

    # 异常 x3
    for i in range(3):
        p = _generate_abnormal_screen(f"abnormal_{i+1:02d}.png", seed=i)
        samples.append((p, "abnormal"))

    return samples


# -----------------------------------------------------------------------------
# 像素方差检测（冷启动，不依赖锚点库 / LLM）
# -----------------------------------------------------------------------------
def detect_screen_type(img_path: Path) -> str:
    """纯像素方差检测（D11 冷启动）。

    判定规则：
    - 均值 > 240 且方差 < 50 -> blank_white
    - 均值 < 15 且方差 < 50 -> blank_black
    - 方差 < 500 且均值 > 200 -> loading（加载中通常大面积浅色 + 少量元素）
    - 方差 > 5000 -> abnormal（过度杂乱）
    - 其他 -> normal

    Returns:
        检测类别字符串。
    """
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img)
    mean = float(arr.mean())
    std = float(arr.std())
    var = std * std

    if mean > 240 and var < 50:
        return "blank_white"
    if mean < 15 and var < 50:
        return "blank_black"
    if var < 500 and mean > 200:
        return "loading"
    if var > 5000:
        return "abnormal"
    return "normal"


# -----------------------------------------------------------------------------
# 混淆矩阵 + 准确率
# -----------------------------------------------------------------------------
def compute_confusion_matrix(
    predictions: list[str],
    ground_truths: list[str],
) -> tuple[dict[str, dict[str, int]], float]:
    """计算混淆矩阵 + 准确率。

    Returns:
        (confusion_matrix, accuracy)
        confusion_matrix[actual][predicted] = count
    """
    labels = sorted(set(ground_truths) | set(predictions))
    matrix: dict[str, dict[str, int]] = {
        actual: {pred: 0 for pred in labels} for actual in labels
    }
    correct = 0
    for pred, gt in zip(predictions, ground_truths, strict=True):
        if gt not in matrix:
            matrix[gt] = {label: 0 for label in labels}
        if pred not in matrix[gt]:
            for actual_label in matrix:
                matrix[actual_label][pred] = 0
            matrix[gt][pred] = 0
        matrix[gt][pred] += 1
        if pred == gt:
            correct += 1

    accuracy = correct / len(predictions) if predictions else 0.0
    return matrix, accuracy


# -----------------------------------------------------------------------------
# 报告生成
# -----------------------------------------------------------------------------
def generate_report(
    samples: list[tuple[Path, str]],
    predictions: list[str],
    matrix: dict[str, dict[str, int]],
    accuracy: float,
    total_samples: int,
) -> str:
    """生成 vision report.md。"""
    # 合并 blank_white + blank_black 为 blank 统计冷启动准确率
    blank_correct = 0
    blank_total = 0
    for ( _, gt), pred in zip(samples, predictions, strict=True):
        if gt in ("blank_white", "blank_black"):
            blank_total += 1
            if pred == gt:
                blank_correct += 1

    labels = sorted(matrix.keys())

    lines = [
        "# 视觉决策 Golden 报告",
        "",
        f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 截图样本数: {len(samples)}（共生成 {total_samples} 张）",
        "> 检测模式: **像素方差检测**（D11 冷启动，锚点库空）",
        "",
        "## 冷启动准确率",
        "",
        f"- **整体准确率: {accuracy * 100:.1f}%**（阈值 >=50%）",
        f"- 状态: {'PASS' if accuracy >= 0.5 else 'BELOW（MVP 不阻塞）'}",
        f"- 白屏/黑屏检出率: {blank_correct}/{blank_total}",
        "",
        "## 混淆矩阵",
        "",
    ]

    # 表头
    header = "| 实际 \\ 预测 |" + "|".join(labels) + "|"
    sep = "|---|" + "|".join(["---"] * len(labels)) + "|"
    lines.append(header)
    lines.append(sep)
    for actual in labels:
        row = f"| {actual} |"
        for pred in labels:
            count = matrix.get(actual, {}).get(pred, 0)
            row += f" {count} |"
        lines.append(row)

    lines.extend(
        [
            "",
            "## 检测逻辑（D11 冷启动）",
            "",
            "```",
            "  均值 > 240 且 方差 < 50     -> blank_white",
            "  均值 < 15  且 方差 < 50     -> blank_black",
            "  方差 < 500  且 均值 > 200   -> loading",
            "  方差 > 5000                -> abnormal",
            "  其他                        -> normal",
            "```",
            "",
            "## 样本明细",
            "",
            "| 文件名 | 人工标注 | 检测结果 | 正确 |",
            "|--------|---------|---------|------|",
        ]
    )

    for (path, gt), pred in zip(samples, predictions, strict=True):
        correct = "YES" if pred == gt else "NO"
        lines.append(f"| {path.name} | {gt} | {pred} | {correct} |")

    lines.extend(
        [
            "",
            "## 结论",
            "",
            f"- 冷启动像素方差检测准确率: {accuracy * 100:.1f}%",
            "- MVP 阶段：方法可执行 + 报告产出即 pass。",
            "- D11 锚点库录入后，BF003 VisualDecisionEngine 会切换到锚点对照模式，"
            "准确率将提升。",
        ]
    )

    return "\n".join(lines) + "\n"


# -----------------------------------------------------------------------------
# 主入口
# -----------------------------------------------------------------------------
def main() -> None:
    """主入口：生成截图 -> 检测 -> 混淆矩阵 -> 报告。"""
    print("Generating screenshot samples...")
    samples = generate_all_samples()
    print(f"Generated {len(samples)} samples in {SAMPLES_DIR}")

    # 像素方差检测
    print("\nRunning pixel variance detection (cold start)...")
    predictions: list[str] = []
    for path, gt in samples:
        pred = detect_screen_type(path)
        predictions.append(pred)
        status = "OK" if pred == gt else "MISS"
        print(f"  [{status}] {path.name}: gt={gt}, pred={pred}")

    # 混淆矩阵
    ground_truths = [gt for _, gt in samples]
    matrix, accuracy = compute_confusion_matrix(predictions, ground_truths)

    print(f"\nAccuracy: {accuracy * 100:.1f}%")

    # 生成报告
    report = generate_report(samples, predictions, matrix, accuracy, len(samples))
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
