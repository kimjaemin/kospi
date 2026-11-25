"""웹앱(docs/)이 읽는 JSON 데이터를 만든다. data/kospi_top30.parquet, data/kospi_index.csv → docs/data/"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kospi import index as kidx  # noqa: E402
from kospi import marcap as mc  # noqa: E402

OUT = ROOT / "docs" / "data"


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def pack(df: pd.DataFrame) -> dict:
    """일자별 행을 {stocks:[[코드,이름]], days:{yyyymmdd:[종목번호,시총(억원),종가,등락률, ...]}} 로 줄인다."""
    stocks: dict[tuple[str, str], int] = {}
    days: dict[str, list] = {}
    for day, g in df.groupby("Date"):
        g = g.sort_values("Marcap", ascending=False)
        common = (~mc.is_preferred(g["Code"])).cumsum()
        g = g[(common <= 10) | (g["Rank"] <= 10)]  # 우선주를 빼도 10개가 남을 만큼만
        row: list = []
        for r in g.itertuples():
            i = stocks.setdefault((r.Code, r.Name), len(stocks))
            row += [i, round(r.Marcap / 1e8), int(r.Close), round(float(r.ChangesRatio), 2)]
        days[f"{day:%Y%m%d}"] = row
    return {"stocks": [list(k) for k in stocks], "days": days}


def main() -> None:
    top = mc.load_top()
    top["Rank"] = top.groupby("Date")["Marcap"].rank(method="first", ascending=False).astype(int)
    dates = pd.DatetimeIndex(sorted(top["Date"].unique()))
    for year, g in top.groupby(top["Date"].dt.year):
        dump(OUT / "top" / f"{year}.json", pack(g))
    ends = mc.period_end_dates(dates, "M")
    dump(OUT / "top" / "monthend.json", pack(top[top["Date"].isin(ends)]))

    idx = kidx.load_index()
    idx["Date"] = pd.to_datetime(idx["Date"])
    if len(idx):
        idx = kidx.resample(idx, "D")
    dump(OUT / "index.json", {
        "d": [int(f"{d:%Y%m%d}") for d in idx["Date"]],
        **{k: [round(float(v), 2) for v in idx[c]] for k, c in zip("ohlc", ["Open", "High", "Low", "Close"])},
    })
    dump(OUT / "meta.json", {
        "topFirst": f"{dates.min():%Y%m%d}", "topLast": f"{dates.max():%Y%m%d}",
        "indexLast": f"{idx['Date'].max():%Y%m%d}" if len(idx) else None,
        "built": pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d %H:%M"),
    })
    print("top", dates.min().date(), "~", dates.max().date(), "| index rows", len(idx))


if __name__ == "__main__":
    main()
