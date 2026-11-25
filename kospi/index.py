"""코스피 지수 일별 시세(시가·고가·저가·종가). 네이버 금융 차트 데이터를 쓰고 data/kospi_index.csv 에 보관한다."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDEX_FILE = DATA_DIR / "kospi_index.csv"
NAVER_URL = "https://fchart.stock.naver.com/sise.nhn"
COLS = ["Date", "Open", "High", "Low", "Close", "Volume"]


def parse_naver(text: str) -> pd.DataFrame:
    items = re.findall(r'<item data="(.*?)"', text)
    if not items:
        raise ValueError("네이버 응답에 지수 데이터가 없습니다.")
    df = pd.read_csv(io.StringIO("\n".join(items)), sep="|", header=None, names=COLS, dtype={"Date": str})
    df["Date"] = pd.to_datetime(df["Date"], format="%Y%m%d")
    return df.sort_values("Date").reset_index(drop=True)


def fetch_naver(count: int = 20000, timeout: int = 30) -> pd.DataFrame:
    r = requests.get(
        NAVER_URL,
        params={"symbol": "KOSPI", "timeframe": "day", "count": count, "requestType": 0},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=timeout,
    )
    r.raise_for_status()
    return parse_naver(r.text)


def fetch_fdr() -> pd.DataFrame:
    import FinanceDataReader as fdr

    df = fdr.DataReader("KS11", "1980-01-01").reset_index()
    df = df.rename(columns={df.columns[0]: "Date"})
    return df[[c for c in COLS if c in df.columns]]


def load_index() -> pd.DataFrame:
    if not INDEX_FILE.exists():
        return pd.DataFrame(columns=COLS[:5])
    return pd.read_csv(INDEX_FILE, parse_dates=["Date"])


def update_index() -> tuple[pd.DataFrame, int]:
    """최신 지수를 받아 저장본과 합친다. (전체 데이터, 추가된 거래일 수)를 돌려준다.

    네이버는 최근 3000거래일만 주므로, 그보다 오래된 구간이 비어 있으면 FinanceDataReader로 채운다.
    """
    cur = load_index()
    try:
        new = fetch_naver()
    except Exception:
        new = fetch_fdr()
    parts = [cur, new]
    oldest = min(p["Date"].min() for p in parts if len(p))
    if oldest > pd.Timestamp("2000-01-01"):
        try:
            old = fetch_fdr()
            parts.insert(0, old[old["Date"] < oldest])
        except Exception:
            pass  # 과거 구간은 다음 갱신 때 다시 시도한다
    cols = ["Date", "Open", "High", "Low", "Close"]
    out = pd.concat([p[cols] for p in parts if len(p)], ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"])
    out = out.dropna(subset=["Close"])
    out = out[out["Close"] > 0].drop_duplicates("Date", keep="last")
    out = out.sort_values("Date").reset_index(drop=True)
    DATA_DIR.mkdir(exist_ok=True)
    out.to_csv(INDEX_FILE, index=False)
    return out, len(out) - len(cur)


def resample(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """일별('D')/월별('M')/연도별('Y') 시세와 등락률. 등락률은 직전 기간 종가 대비."""
    d = df.copy()
    # 옛 자료는 시가·고가·저가가 0으로 비어 있는 날이 있어 종가로 채운다
    for c in ["Open", "High", "Low"]:
        d[c] = d[c].where(d[c] > 0, d["Close"])
    if freq != "D":
        g = d.groupby(d["Date"].dt.to_period(freq))
        d = g.agg(Date=("Date", "max"), Open=("Open", "first"), High=("High", "max"),
                  Low=("Low", "min"), Close=("Close", "last"), Days=("Close", "size")).reset_index(drop=True)
    d["Change"] = d["Close"].diff()
    d["ChangePct"] = d["Close"].pct_change() * 100
    return d
