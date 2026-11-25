"""시가총액·코스피 지수를 최신으로 받고 웹앱 데이터(docs/data)를 다시 만든다. GitHub Actions가 매일 실행한다."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kospi import index as kidx  # noqa: E402
from kospi import marcap as mc  # noqa: E402
from scripts import build_web_data  # noqa: E402

failed = []
for name, fn in [("시가총액", mc.update_top), ("코스피 지수", kidx.update_index)]:
    try:
        df, added = fn()
        print(f"{name}: {added}거래일 추가, 최근 {df['Date'].max():%Y-%m-%d}")
    except Exception:
        traceback.print_exc()
        failed.append(name)
build_web_data.main()
if failed:  # 받은 것까지는 반영하고, 실패는 실행 기록에 남긴다
    sys.exit(f"갱신 실패: {', '.join(failed)}")
