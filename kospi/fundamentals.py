"""코스피 종목별 사업분야와 PER·PBR·EPS·BPS 최신 스냅샷. data/kospi_fundamentals.csv 에 보관한다.

원본(모두 로그인·키 불필요):
- 네이버 증권 모바일 JSON API: 시가총액 목록(종목·종가·시총), 업종 목록(업종 번호→이름),
  종목별 integration(업종 번호, PER·EPS·PBR·BPS).
- KIND 상장법인목록: 주요제품. 받지 못해도 나머지는 그대로 만든다.
"""
from __future__ import annotations

import io
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FUND_FILE = DATA_DIR / "kospi_fundamentals.csv"
NAVER_API = "https://m.stock.naver.com/api"
KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
}
COLS = ["Date", "Code", "Name", "Sector", "Products", "Close", "Marcap", "Shares", "PER", "PBR", "EPS", "BPS"]
SECTOR_COLS = ["Sector", "Count", "PER", "PBR", "EPS"]
PAGE_SIZE = 100  # 네이버 목록 API의 최대값(더 크면 400)
WORKERS = 8
RETRIES = 4


def _get_json(session: requests.Session, url: str, params: dict | None = None, timeout: int = 15):
    """실패하면 잠깐 쉬었다 다시 시도한다."""
    for i in range(RETRIES):
        try:
            r = session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if i == RETRIES - 1:
                raise
            time.sleep(1.5 * (i + 1))


def _num(text) -> float:
    """'31,809원', '5.25배', 'N/A' 같은 표기를 숫자로. 숫자가 아니면 NaN."""
    s = str(text).replace(",", "").rstrip("원배%").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def fetch_listing(session: requests.Session) -> pd.DataFrame:
    """코스피 시가총액 목록에서 주식(보통주+우선주)만. ETF·ETN은 뺀다."""
    rows, page = [], 1
    while True:
        j = _get_json(session, f"{NAVER_API}/stocks/marketValue/KOSPI", {"page": page, "pageSize": PAGE_SIZE})
        stocks = j.get("stocks") or []
        rows += [s for s in stocks if s.get("stockEndType") == "stock"]
        if len(stocks) < PAGE_SIZE or page * PAGE_SIZE >= int(j.get("totalCount") or 0):
            break
        page += 1
    if not rows:
        raise ValueError("네이버 응답에 종목 목록이 없습니다.")
    df = pd.DataFrame({
        "Date": [s["localTradedAt"][:10] for s in rows],
        "Code": [s["itemCode"] for s in rows],
        "Name": [s["stockName"] for s in rows],
        "Close": [float(s["closePriceRaw"]) for s in rows],
        "Marcap": [float(s["marketValueRaw"]) for s in rows],
    })
    df["Date"] = df["Date"].max()  # 거래정지 종목도 같은 기준일로 맞춘다
    df["Shares"] = (df["Marcap"] / df["Close"]).round()  # 목록에 주식수가 없어 시총÷종가로 구한다
    return df.drop_duplicates("Code")


def fetch_sector_names(session: requests.Session) -> dict[str, str]:
    """네이버 업종 번호 → 업종명(약 80개)."""
    j = _get_json(session, f"{NAVER_API}/stocks/industry", {"page": 1, "pageSize": PAGE_SIZE})
    return {str(g["no"]): g["name"] for g in j.get("groups") or []}


def fetch_one(session: requests.Session, code: str) -> dict:
    """종목 하나의 업종 번호와 PER·PBR·EPS·BPS. 끝내 실패하면 빈 값으로 둔다."""
    out = {"Code": code, "SectorNo": None, "PER": float("nan"), "PBR": float("nan"),
           "EPS": float("nan"), "BPS": float("nan")}
    try:
        j = _get_json(session, f"{NAVER_API}/stock/{code}/integration")
    except (requests.RequestException, ValueError):
        return out
    if j.get("industryCode"):
        out["SectorNo"] = str(j["industryCode"])
    for info in j.get("totalInfos") or []:
        key = str(info.get("code", "")).upper()
        if key in ("PER", "PBR", "EPS", "BPS"):
            out[key] = _num(info.get("value"))
    return out


def fetch_products(timeout: int = 30) -> dict[str, str]:
    """KIND 상장법인목록(유가증권)의 종목코드 → 주요제품. EUC-KR HTML 표로 내려온다."""
    r = requests.post(KIND_URL, data={"method": "download", "marketType": "stockMkt"},
                      headers={"User-Agent": HEADERS["User-Agent"]}, timeout=timeout)
    r.raise_for_status()
    t = pd.read_html(io.StringIO(r.content.decode("euc-kr", "replace")), converters={"종목코드": str})[0]
    t["종목코드"] = t["종목코드"].str.zfill(6)
    products = t["주요제품"].fillna("").astype(str).str.strip().replace("-", "")  # '-'는 내용 없음 표시
    return dict(zip(t["종목코드"], products))


def fetch_fundamentals() -> pd.DataFrame:
    """코스피 전 종목(보통주+우선주)의 최신 스냅샷."""
    session = requests.Session()
    session.headers.update(HEADERS)
    df = fetch_listing(session)
    names = fetch_sector_names(session)
    with ThreadPoolExecutor(WORKERS) as ex:
        detail = pd.DataFrame(ex.map(lambda c: fetch_one(session, c), df["Code"]))
    df = df.merge(detail, on="Code", how="left")
    df["Sector"] = df["SectorNo"].map(names).fillna("")
    try:
        products = fetch_products()
    except Exception:
        products = {}  # KIND가 막혀도 나머지 데이터는 살린다
    # 우선주는 KIND 목록에 없어 보통주(앞 5자리+0)의 주요제품을 쓴다
    common = df["Code"].str[:5] + "0"
    df["Products"] = df["Code"].map(products).fillna(common.map(products)).fillna("")
    return df.sort_values("Marcap", ascending=False)[COLS].reset_index(drop=True)


def update_fundamentals() -> tuple[pd.DataFrame, int]:
    """새로 받아 저장한다(덮어쓰기). (데이터, 종목 수)를 돌려준다."""
    df = fetch_fundamentals()
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(FUND_FILE, index=False)
    return df, len(df)


def load_fundamentals() -> pd.DataFrame:
    if not FUND_FILE.exists():
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(FUND_FILE, dtype={"Code": str, "Date": str, "Name": str, "Sector": str, "Products": str})
    df[["Sector", "Products"]] = df[["Sector", "Products"]].fillna("")
    return df[COLS]


def sector_averages(df: pd.DataFrame) -> pd.DataFrame:
    """업종별 PER·PBR·EPS. 우선주(종목코드 끝자리가 0이 아님)와 업종 없는 종목은 뺀다.

    PER = 시총 합 ÷ 순이익 합(EPS×주식수, 적자 포함, 합이 0 이하면 NaN),
    PBR = 시총 합 ÷ 순자산 합(BPS×주식수), EPS = 단순평균. Count는 EPS가 있는 종목 수.
    """
    d = df[(df["Code"].str[-1] == "0") & (df["Sector"].fillna("") != "")]
    rows = []
    for sector, g in d.groupby("Sector"):
        e = g.dropna(subset=["EPS", "Shares", "Marcap"])
        b = g.dropna(subset=["BPS", "Shares", "Marcap"])
        profit = (e["EPS"] * e["Shares"]).sum()
        equity = (b["BPS"] * b["Shares"]).sum()
        rows.append({
            "Sector": sector,
            "Count": len(e),
            "PER": e["Marcap"].sum() / profit if profit > 0 else float("nan"),
            "PBR": b["Marcap"].sum() / equity if equity > 0 else float("nan"),
            "EPS": e["EPS"].mean() if len(e) else float("nan"),
        })
    return pd.DataFrame(rows, columns=SECTOR_COLS)
