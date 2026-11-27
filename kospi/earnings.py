"""실적·컨센서스 자료 읽기. 수집 코드와 데이터는 개인용(Mac)으로만 쓰고 공개 저장소에는 넣지 않는다.

data/kospi_earnings.json 이 없으면 앱은 종목별 분석 칸을 숨긴다.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EARN_FILE = DATA_DIR / "kospi_earnings.json"


def load_earnings() -> dict:
    if not EARN_FILE.exists():
        return {"date": None, "stocks": {}}
    return json.loads(EARN_FILE.read_text(encoding="utf-8"))


def update_earnings(n: int = 30):
    raise NotImplementedError("이 저장소에는 실적·전망치 수집 코드가 포함되어 있지 않습니다.")
