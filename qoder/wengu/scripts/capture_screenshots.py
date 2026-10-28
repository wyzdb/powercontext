"""批量截图：把 evidence/qoder/ 的 10 个 HTML 转成 PNG。"""

import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML_DIR = ROOT / "evidence" / "qoder"
OUTPUT_DIR = HTML_DIR

FILES = [
    "01-需求拆解.html",
    "02-连通性验证.html",
    "03-数据管道.html",
    "04-混合检索.html",
    "05-记忆跨会话.html",
    "06-应用层.html",
    "07-复习闭环.html",
    "08-交付打包.html",
    "09-commit 时间线.html",
    "10-Qoder-UID.html",
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        for i, fname in enumerate(FILES, 1):
            html_path = HTML_DIR / fname
            if not html_path.exists():
                print(f"[{i}/10] 跳过 {fname}（文件不存在）")
                continue

            png_name = fname.replace(".html", ".png")
            png_path = OUTPUT_DIR / png_name

            page.goto(f"file:///{html_path.as_posix()}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(png_path), full_page=True)
            print(f"[{i}/10] {png_name} ({png_path.stat().st_size // 1024}KB)")

        browser.close()

    print(f"\n完成！截图保存在：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
