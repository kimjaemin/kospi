"""코스피 분석기: 시가총액 상위 10 종목과 코스피 지수를 일별·월별·연도별로 본다.

실행: streamlit run app.py
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from kospi import index as kidx
from kospi import marcap as mc

UP, DOWN, LINE = "#d6453d", "#2f6fd0", "#2f6fd0"  # 국내 관례: 상승 빨강, 하락 파랑
JO = 1e12  # 1조원

st.set_page_config(page_title="코스피 분석기", page_icon="📈", layout="wide")


# ---------- 데이터 ----------
def last_weekday(now: dt.datetime) -> pd.Timestamp:
    """지금 시점에 데이터가 있을 법한 가장 최근 평일(장 마감 전이면 전날)."""
    d = now.date() if now.hour >= 18 else now.date() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return pd.Timestamp(d)


@st.cache_data(ttl=6 * 3600, show_spinner="시가총액 데이터를 확인하는 중…")
def get_top() -> tuple[pd.DataFrame, str | None]:
    df = mc.load_top()
    if len(df) and df["Date"].max() >= last_weekday(dt.datetime.now()):
        return df, None
    try:
        return mc.update_top()[0], None
    except Exception as e:  # 오프라인이어도 저장된 데이터로 계속 쓴다
        return df, f"시가총액 데이터를 새로 받지 못해 저장된 데이터를 보여줍니다. ({type(e).__name__})"


@st.cache_data(ttl=6 * 3600, show_spinner="코스피 지수를 확인하는 중…")
def get_index() -> tuple[pd.DataFrame, str | None]:
    df = kidx.load_index()
    if len(df) and df["Date"].max() >= last_weekday(dt.datetime.now()):
        return df, None
    try:
        return kidx.update_index()[0], None
    except Exception as e:
        return df, f"코스피 지수를 새로 받지 못해 저장된 데이터를 보여줍니다. ({type(e).__name__})"


# ---------- 시가총액 상위 10 ----------
def detail(top: pd.DataFrame, day: pd.Timestamp, title: str) -> None:
    d = top[top["Date"] == day].copy()
    d["조원"] = d["Marcap"] / JO
    st.subheader(title)
    st.caption(f"기준일 {day:%Y-%m-%d} 종가 · 상위 10개 합계 {d['조원'].sum():,.1f}조원")
    left, right = st.columns([5, 4])
    table = pd.DataFrame({
        "순위": d["Rank"], "종목명": d["Name"], "종목코드": d["Code"],
        "종가(원)": d["Close"], "등락률(%)": d["ChangesRatio"], "시가총액(조원)": d["조원"],
    })
    left.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "종가(원)": st.column_config.NumberColumn(format="localized"),
            "등락률(%)": st.column_config.NumberColumn(format="%.2f"),
            "시가총액(조원)": st.column_config.NumberColumn(format="%.1f"),
        },
    )
    left.download_button("CSV 내려받기", table.to_csv(index=False).encode("utf-8-sig"),
                         f"kospi_top10_{day:%Y%m%d}.csv", "text/csv")
    fig = go.Figure(go.Bar(
        x=d["조원"], y=d["Name"], orientation="h", marker_color=LINE,
        text=d["조원"].map("{:,.1f}".format), textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:,.1f}조원<extra></extra>",
    ))
    fig.update_layout(height=380, margin=dict(l=0, r=50, t=10, b=0), xaxis_title="시가총액(조원)",
                      yaxis=dict(autorange="reversed"))
    right.plotly_chart(fig, width="stretch")


def matrix(top: pd.DataFrame, days: pd.DatetimeIndex, fmt: str, caption: str) -> None:
    m = top[top["Date"].isin(days)].pivot(index="Rank", columns="Date", values="Name")
    m.columns = [c.strftime(fmt) for c in m.columns]
    m.index.name = "순위"
    st.caption(caption)
    st.dataframe(m, width="stretch")


def page_top(basis: str, exclude_pref: bool) -> None:
    raw, warn = get_top()
    if warn:
        st.warning(warn)
    if raw.empty:
        st.error("시가총액 데이터가 없습니다. 인터넷 연결을 확인한 뒤 '데이터 새로 받기'를 눌러 주세요.")
        return
    top = mc.top_n(raw, 10, exclude_pref)
    days = pd.DatetimeIndex(sorted(top["Date"].unique()))
    first, last = days.min(), days.max()
    st.title("코스피 시가총액 상위 10")
    st.caption(f"데이터 기간 {first:%Y-%m-%d} ~ {last:%Y-%m-%d} · 출처 한국거래소 전종목 시세(marcap 데이터셋)"
               + (" · 우선주 제외" if exclude_pref else " · 우선주 포함"))

    if basis == "일별":
        pick = st.date_input("날짜", last.date(), min_value=first.date(), max_value=last.date())
        day = mc.trading_day_on_or_before(days, pick)
        if day.date() != pick:
            st.info(f"{pick:%Y-%m-%d}은 휴장일이라 직전 거래일({day:%Y-%m-%d}) 기준으로 보여줍니다.")
        detail(top, day, f"{day:%Y년 %m월 %d일} 시가총액 상위 10")

    elif basis == "월별":
        ends = mc.period_end_dates(days, "M")
        years = sorted(ends.year.unique(), reverse=True)
        c1, c2 = st.columns(2)
        year = c1.selectbox("연도", years)
        in_year = ends[ends.year == year]
        month = c2.selectbox("월", list(in_year.month), index=len(in_year) - 1, format_func=lambda m: f"{m}월")
        day = in_year[in_year.month == month][0]
        detail(top, day, f"{year}년 {month}월 말 시가총액 상위 10" if day != last else f"{year}년 {month}월 시가총액 상위 10 (최근 거래일)")
        st.subheader(f"{year}년 월별 순위 변화")
        matrix(top, in_year, "%m월", "각 월의 마지막 거래일 기준입니다.")

    else:
        ends = mc.period_end_dates(days, "Y")
        years = list(ends.year)
        lo, hi = st.select_slider("연도 범위", years, value=(max(years[0], years[-1] - 9), years[-1]))
        year = st.selectbox("자세히 볼 연도", [y for y in reversed(years) if lo <= y <= hi])
        day = ends[ends.year == year][0]
        detail(top, day, f"{year}년 말 시가총액 상위 10" if day != last else f"{year}년 시가총액 상위 10 (최근 거래일)")
        st.subheader(f"{lo}~{hi}년 연도별 순위 변화")
        matrix(top, ends[(ends.year >= lo) & (ends.year <= hi)], "%Y",
               f"각 연도의 마지막 거래일 기준입니다. {last.year}년은 {last:%m월 %d일} 기준입니다.")


# ---------- 코스피 지수 ----------
def index_charts(d: pd.DataFrame, basis: str, label_fmt: str) -> None:
    fig = go.Figure(go.Scatter(
        x=d["Date"], y=d["Close"], mode="lines", line=dict(color=LINE, width=2), name="종가",
        customdata=d[["Open", "High", "Low", "ChangePct"]],
        hovertemplate=("%{x|" + label_fmt + "}<br>종가 %{y:,.2f}<br>시가 %{customdata[0]:,.2f} · 고가 %{customdata[1]:,.2f}"
                       " · 저가 %{customdata[2]:,.2f}<br>등락률 %{customdata[3]:+.2f}%<extra></extra>"),
    ))
    fig.update_layout(height=420, margin=dict(l=0, r=10, t=10, b=0), yaxis_title="코스피 지수(종가)",
                      hovermode="x")
    st.plotly_chart(fig, width="stretch")
    if basis != "일별":
        b = d.dropna(subset=["ChangePct"])
        fig2 = go.Figure(go.Bar(
            x=b["Date"].dt.strftime(label_fmt), y=b["ChangePct"],
            marker_color=[UP if v >= 0 else DOWN for v in b["ChangePct"]],
            hovertemplate="%{x}<br>등락률 %{y:+.2f}%<extra></extra>",
        ))
        fig2.update_layout(height=300, margin=dict(l=0, r=10, t=10, b=0), yaxis_title=f"{basis[:-1]}간 등락률(%)",
                           xaxis=dict(type="category", nticks=20))
        st.caption("등락률은 직전 기간 종가 대비입니다. 빨강은 상승, 파랑은 하락입니다.")
        st.plotly_chart(fig2, width="stretch")


def page_index(basis: str) -> None:
    raw, warn = get_index()
    if warn:
        st.warning(warn)
    if raw.empty:
        st.error("코스피 지수 데이터가 없습니다. 인터넷 연결을 확인한 뒤 '데이터 새로 받기'를 눌러 주세요.")
        return
    first, last = raw["Date"].min(), raw["Date"].max()
    st.title("코스피 지수")
    st.caption(f"데이터 기간 {first:%Y-%m-%d} ~ {last:%Y-%m-%d} · 출처 네이버 금융·FinanceDataReader")

    if basis == "일별":
        d = kidx.resample(raw, "D")
        span = st.radio("기간", ["1개월", "3개월", "1년", "5년", "전체", "직접 선택"], index=2, horizontal=True)
        months = {"1개월": 1, "3개월": 3, "1년": 12, "5년": 60}
        if span == "직접 선택":
            c1, c2 = st.columns(2)
            start = c1.date_input("시작일", (last - pd.DateOffset(years=1)).date(), min_value=first.date(), max_value=last.date())
            end = c2.date_input("종료일", last.date(), min_value=first.date(), max_value=last.date())
        else:
            start = first.date() if span == "전체" else (last - pd.DateOffset(months=months[span])).date()
            end = last.date()
        fmt, col = "%Y-%m-%d", "날짜"
    elif basis == "월별":
        d = kidx.resample(raw, "M")
        years = list(range(first.year, last.year + 1))
        lo, hi = st.select_slider("연도 범위", years, value=(max(years[0], years[-1] - 4), years[-1]))
        start, end = dt.date(lo, 1, 1), dt.date(hi, 12, 31)
        fmt, col = "%Y-%m", "월"
    else:
        d = kidx.resample(raw, "Y")
        years = list(range(first.year, last.year + 1))
        lo, hi = st.select_slider("연도 범위", years, value=(years[0], years[-1]))
        start, end = dt.date(lo, 1, 1), dt.date(hi, 12, 31)
        fmt, col = "%Y", "연도"

    d = d[(d["Date"] >= pd.Timestamp(start)) & (d["Date"] <= pd.Timestamp(end))]
    if d.empty:
        st.info("선택한 기간에 데이터가 없습니다.")
        return

    # 기준은 선택한 기간이 시작되기 직전 종가(월별·연도별의 d["Date"]는 각 기간의 마지막 거래일이라 기준으로 쓸 수 없다)
    base = raw.loc[raw["Date"] < pd.Timestamp(start), "Close"]
    base = base.iloc[-1] if len(base) else d["Open"].iloc[0]
    hi_row, lo_row = d.loc[d["High"].idxmax()], d.loc[d["Low"].idxmin()]
    c = st.columns(4)
    c[0].metric(f"종가 ({d['Date'].iloc[-1]:%Y-%m-%d})", f"{d['Close'].iloc[-1]:,.2f}")
    c[1].metric("기간 등락률", f"{(d['Close'].iloc[-1] / base - 1) * 100:+.2f}%")
    c[2].metric(f"기간 최고 ({hi_row['Date']:{fmt}})", f"{hi_row['High']:,.2f}")
    c[3].metric(f"기간 최저 ({lo_row['Date']:{fmt}})", f"{lo_row['Low']:,.2f}")

    index_charts(d, basis, fmt)

    table = pd.DataFrame({
        col: d["Date"].dt.strftime(fmt), "시가": d["Open"], "고가": d["High"], "저가": d["Low"],
        "종가": d["Close"], "전기 대비": d["Change"], "등락률(%)": d["ChangePct"],
    }).iloc[::-1]
    num = st.column_config.NumberColumn(format="%.2f")
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={k: num for k in table.columns[1:]})
    st.download_button("CSV 내려받기", table.to_csv(index=False).encode("utf-8-sig"),
                       f"kospi_index_{basis}.csv", "text/csv")


# ---------- 화면 ----------
with st.sidebar:
    st.header("코스피 분석기")
    page = st.radio("보기", ["시가총액 상위 10", "코스피 지수"])
    basis = st.radio("기준", ["일별", "월별", "연도별"], horizontal=True)
    exclude_pref = False
    if page == "시가총액 상위 10":
        exclude_pref = st.checkbox("우선주 제외", help="삼성전자우 같은 우선주를 순위에서 뺍니다.")
    st.divider()
    if st.button("데이터 새로 받기"):
        st.cache_data.clear()
        for name, fn in [("시가총액", mc.update_top), ("코스피 지수", kidx.update_index)]:
            try:
                with st.spinner(f"{name} 받는 중…"):
                    st.success(f"{name}: {fn()[1]}거래일 추가")
            except Exception as e:
                st.error(f"{name} 실패: {e}")

if page == "시가총액 상위 10":
    page_top(basis, exclude_pref)
else:
    page_index(basis)
