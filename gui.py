"""코스피 분석기를 전용 창으로 연다. 창을 닫으면 프로그램도 함께 끝난다.

실행: python gui.py  (Mac에서는 '코스피 분석기.app' 더블클릭)
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TITLE = "코스피 분석기"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(url: str, proc: subprocess.Popen, timeout: float = 90) -> bool:
    end = time.time() + timeout
    while time.time() < end and proc.poll() is None:
        try:
            with urllib.request.urlopen(url + "/_stcore/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.3)
    return False


def main() -> int:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
         "--server.headless", "true", "--server.address", "127.0.0.1", "--server.port", str(port),
         "--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal"],
        cwd=ROOT,
    )
    try:
        if not wait_ready(url, proc):
            print("프로그램을 시작하지 못했습니다.", file=sys.stderr)
            return 1
        try:
            import webview
        except ImportError:  # 전용 창을 못 쓰면 기본 브라우저로 연다
            import webbrowser

            webbrowser.open(url)
            proc.wait()
            return 0
        webview.settings["ALLOW_DOWNLOADS"] = True  # CSV 내려받기
        webview.create_window(TITLE, url, width=1440, height=920, min_size=(900, 600))
        webview.start()
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
