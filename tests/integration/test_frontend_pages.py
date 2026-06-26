"""
前端页面冒烟测试 — Playwright 驱动真实浏览器验证 /gaps 和 /clarify 页面

验证契约对齐修复后页面不再崩溃：
  - /gaps：gapApi.list() 解包 {items,...} → CapabilityGap[]
  - /reports/:id/clarify：clarifyApi.options() 解包 {options:[...]} → ClarifyOption[]
  - gap_type: "repro"（非枚举值）不崩溃

运行方式：
  python tests/integration/test_frontend_pages.py
  前提：frontend dev server (localhost:5173) + backend (localhost:8002) 已启动
"""

import sys
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:5173"
BACKEND = "http://localhost:8002"


def collect_errors(page):
    """收集浏览器 console 错误和页面未捕获异常"""
    errors = []
    page.on("pageerror", lambda err: errors.append(f"pageerror: {err}"))
    page.on("console", lambda msg: errors.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None)
    return errors


def test_gaps_page(page):
    """验证 /gaps 页面正常渲染"""
    errors = collect_errors(page)

    page.goto(f"{FRONTEND}/gaps", wait_until="networkidle")
    page.wait_for_timeout(2000)

    title = page.title()
    print(f"  页面标题: {title}")

    # 验证 antd List 渲染了缺口项（不是空白/崩溃）
    list_items = page.query_selector_all(".ant-list-item")
    print(f"  渲染缺口数: {len(list_items)}")

    # 验证有 Tag 组件渲染（说明 gap_type 不崩溃）
    tags = page.query_selector_all(".ant-tag")
    print(f"  Tag 数量: {len(tags)}")

    # 验证页面没有崩溃错误
    crash_errors = [e for e in errors if "TypeError" in e or "is not a function" in e or "is not iterable" in e]
    if crash_errors:
        print(f"  ❌ 崩溃错误: {crash_errors}")
        return False

    if len(list_items) == 0:
        print("  ❌ 缺口列表为空（可能未渲染）")
        return False

    print("  ✅ /gaps 页面正常渲染，无崩溃")
    return True


def test_clarify_page(page):
    """验证 /reports/:id/clarify 页面正常渲染"""
    errors = collect_errors(page)

    # 使用后端真实存在的报告 ID
    page.goto(f"{FRONTEND}/reports/demo-001/clarify", wait_until="networkidle")
    page.wait_for_timeout(2000)

    title = page.title()
    print(f"  页面标题: {title}")

    # 验证没有 options.map 崩溃
    crash_errors = [e for e in errors if "map" in e.lower() and "function" in e.lower()]
    if crash_errors:
        print(f"  ❌ options.map 崩溃: {crash_errors}")
        return False

    # 验证页面有内容渲染（Empty 组件或 Form）
    body_text = page.inner_text("body")
    print(f"  页面内容: {body_text[:100]}...")

    crash_errors = [e for e in errors if "TypeError" in e or "is not a function" in e]
    if crash_errors:
        print(f"  ❌ 崩溃错误: {crash_errors}")
        return False

    print("  ✅ /clarify 页面正常渲染，无崩溃")
    return True


def test_report_detail_page(page):
    """验证 /reports/:id 详情页正常（含 trajectory + regression）"""
    errors = collect_errors(page)

    page.goto(f"{FRONTEND}/reports/demo-001", wait_until="networkidle")
    page.wait_for_timeout(2000)

    crash_errors = [e for e in errors if "TypeError" in e or "is not a function" in e]
    if crash_errors:
        print(f"  ❌ 崩溃错误: {crash_errors}")
        return False

    body_text = page.inner_text("body")
    print(f"  页面内容: {body_text[:100]}...")
    print("  ✅ /reports/:id 详情页正常渲染")
    return True


def main():
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        print("\n=== 前端页面冒烟测试 ===\n")

        print("[1/3] /gaps 页面")
        results["gaps"] = test_gaps_page(page)

        # 新页面避免 errors 累积
        page2 = context.new_page()
        print("\n[2/3] /reports/demo-001/clarify 页面")
        results["clarify"] = test_clarify_page(page2)

        page3 = context.new_page()
        print("\n[3/3] /reports/demo-001 详情页")
        results["report_detail"] = test_report_detail_page(page3)

        browser.close()

    print("\n=== 结果汇总 ===")
    all_pass = True
    for name, ok in results.items():
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {name}: {status}")
        if not ok:
            all_pass = False

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
