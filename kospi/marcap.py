"""코스피 시가총액 상위 종목 데이터.

원본: FinanceData/marcap 데이터셋(한국거래소 전종목 시세, 1995-05-02~, 매일 갱신).
연도별 원본 파일(약 20MB)에서 코스피 일자별 상위 30종목만 추려 data/kospi_top30.parquet 에 보관한다.
"""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOP_FILE = DATA_DIR / "kospi_top30.parquet"
RAW_URL = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{year}.parquet"
KEEP = 30
COLS = ["Date", "Rank", "Code", "Name", "Close", "ChangesRatio", "Marcap", "Stocks"]


def extract_top(raw: pd.DataFrame, keep: int = KEEP) -> pd.DataFrame:
    """전종목 원본에서 코스피 일자별 시총 상위 keep개를 뽑는다."""
    df = raw[raw["Market"] == "KOSPI"].copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
    df["Code"] = df["Code"].astype(str).str.zfill(6)
    df = df[df["Marcap"] > 0]
    df["Rank"] = df.groupby("Date")["Marcap"].rank(method="first", ascending=False).astype(int)
    df = df[df["Rank"] <= keep].sort_values(["Date", "Rank"])
    return df[COLS].reset_index(drop=True)


def load_top() -> pd.DataFrame:
    if not TOP_FILE.exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_parquet(TOP_FILE)


def fetch_year(year: int, timeout: int = 120) -> pd.DataFrame:
    r = requests.get(RAW_URL.format(year=year), timeout=timeout)
    r.raise_for_status()
    return pd.read_parquet(io.BytesIO(r.content))


def update_top(today: dt.date | None = None) -> tuple[pd.DataFrame, int]:
    """저장된 마지막 날짜 이후의 데이터를 내려받아 덧붙인다. (전체 데이터, 추가된 거래일 수)를 돌려준다."""
    today = today or dt.date.today()
    cur = load_top()
    last = cur["Date"].max() if len(cur) else pd.Timestamp("1995-01-01")
    parts = [cur]
    for year in range(max(last.year, 1995), today.year + 1):
        try:
            new = extract_top(fetch_year(year))
        except requests.HTTPError as e:  # 새해 첫 며칠은 해당 연도 파일이 아직 없을 수 있다
            if e.response is not None and e.response.status_code == 404:
                continue
            raise
        parts.append(new[new["Date"] > last])
    out = pd.concat([p for p in parts if len(p)], ignore_index=True)
    out = out.drop_duplicates(["Date", "Code"]).sort_values(["Date", "Rank"]).reset_index(drop=True)
    added = out["Date"].nunique() - cur["Date"].nunique()
    if added > 0:
        DATA_DIR.mkdir(exist_ok=True)
        out.to_parquet(TOP_FILE, index=False)
    return out, added


def is_preferred(code: pd.Series) -> pd.Series:
    """우선주 여부: 종목코드 끝자리가 0이 아니면 우선주."""
    return code.str[-1] != "0"


def top_n(df: pd.DataFrame, n: int = 10, exclude_preferred: bool = False) -> pd.DataFrame:
    """일자별 상위 n개로 다시 순위를 매긴다."""
    if exclude_preferred:
        df = df[~is_preferred(df["Code"])]
    df = df.copy()
    df["Rank"] = df.groupby("Date")["Marcap"].rank(method="first", ascending=False).astype(int)
    return df[df["Rank"] <= n].sort_values(["Date", "Rank"]).reset_index(drop=True)


def period_end_dates(dates: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    """각 월('M')/연('Y')의 마지막 거래일."""
    s = pd.Series(dates, index=dates)
    return pd.DatetimeIndex(s.groupby(dates.to_period(freq)).max().values)


def trading_day_on_or_before(dates: pd.DatetimeIndex, day) -> pd.Timestamp | None:
    d = dates[dates <= pd.Timestamp(day)]
    return d.max() if len(d) else None
