"""코스피 분석기: 시가총액 상위 종목과 코스피 지수를 일별·월별·연도별로 본다.

실행: streamlit run app.py
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from kospi import analysis as kana
from kospi import earnings as kearn
from kospi import fundamentals as kfund
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


@st.cache_data(ttl=24 * 3600, show_spinner="종목 지표(PER·PBR·EPS)를 확인하는 중…")
def get_fund() -> tuple[pd.DataFrame, str | None]:
    df = kfund.load_fundamentals()
    if len(df) and pd.Timestamp(str(df["Date"].iloc[0])) >= last_weekday(dt.datetime.now()):
        return df, None
    try:
        return kfund.update_fundamentals()[0], None
    except Exception as e:
        return df, f"종목 지표를 새로 받지 못했습니다. ({type(e).__name__})"


@st.cache_data(ttl=24 * 3600, show_spinner="실적·전망치를 확인하는 중…")
def get_analysis() -> tuple[dict, str | None]:
    """종목별 분석 문장과 실적 기준일. 종목 지표를 먼저 최신으로 맞춘 뒤 만든다."""
    fund, _ = get_fund()
    earn = kearn.load_earnings()
    if not earn.get("date") or pd.Timestamp(earn["date"]) < last_weekday(dt.datetime.now()):
        try:
            earn = kearn.update_earnings()[0]
        except Exception:
            pass  # 새로 받지 못하면 저장된 것으로 만든다
    return kana.build_all(fund, earn), earn.get("date")


VERDICT_ICON = {"저평가 구간": "🔵", "고평가 구간": "🔴", "중립": "⚪", "판단 보류": "➖"}


def analysis_section(d: pd.DataFrame) -> None:
    """표에 나온 종목별로 실적 대 전망치, 가이던스, 펀더멘털 판단을 펼쳐 보여준다."""
    notes, asof = get_analysis()
    rows = [(r.Rank, r.Name, notes[r.Code]) for r in d.itertuples() if r.Code in notes]
    if not rows:
        return
    st.subheader("종목별 분석")
    st.caption(f"{asof} 기준 최신 자료로 자동 작성했습니다. 출처: 네이버 금융·WiseReport(실적, 증권사 전망치, 목표주가)와 거래소 공시. "
               + kana.DISCLAIMER)
    for rank, name, n in rows:
        with st.expander(f"{rank}. {name} · {VERDICT_ICON.get(n['verdict'], '')} {n['verdict']}"):
            st.markdown(f"**분기 실적과 시장 전망치** · {n['results']}")
            st.markdown(f"**가이던스와 전망** · {n['guidance']}")
            st.markdown(f"**펀더멘털** · {n['fundamental']}")
            st.markdown(f"**판단: {n['verdict']}** · " + ("근거: " + "; ".join(n["signals"]) if n["signals"] else "뚜렷한 신호가 없습니다."))
    st.caption(kana.CRITERIA)


# ---------- 시가총액 상위 종목 ----------
def fund_table(codes: pd.Series) -> tuple[pd.DataFrame, str | None]:
    """종목코드 순서대로 사업분야·PER·PBR·EPS와 업종 평균을 붙인 표와 지표 기준일."""
    fund, _ = get_fund()
    out = pd.DataFrame({"Code": codes.values})
    if fund.empty:
        return out, None
    avg = kfund.sector_averages(fund).rename(columns={"PER": "S_PER", "PBR": "S_PBR", "EPS": "S_EPS"})
    f = fund[["Code", "Sector", "Products", "PER", "PBR", "EPS"]].merge(avg, on="Sector", how="left")
    f["S_EPS"] = f["S_EPS"].round()
    return out.merge(f, on="Code", how="left"), str(fund["Date"].iloc[0])[:10]


def detail(top: pd.DataFrame, day: pd.Timestamp, title: str) -> None:
    d = top[top["Date"] == day].copy()
    d["조원"] = d["Marcap"] / JO
    n = len(d)
    st.subheader(title)
    st.caption(f"기준일 {day:%Y-%m-%d} 종가 · 상위 {n}개 합계 {d['조원'].sum():,.1f}조원")
    f, fund_day = fund_table(d["Code"])
    table = pd.DataFrame({
        "순위": d["Rank"].values, "종목명": d["Name"].values, "종목코드": d["Code"].values,
        "시가총액(조원)": d["조원"].values, "종가(원)": d["Close"].values, "등락률(%)": d["ChangesRatio"].values,
    })
    if fund_day:
        table.insert(3, "사업분야(업종)", f["Sector"].values)
        for src, col in [("PER", "PER"), ("S_PER", "업종 PER"), ("PBR", "PBR"), ("S_PBR", "업종 PBR"),
                         ("EPS", "EPS(원)"), ("S_EPS", "업종 평균 EPS(원)"), ("Products", "주요 제품·사업")]:
            table[col] = f[src].values
    two = st.column_config.NumberColumn(format="%.2f")
    won = st.column_config.NumberColumn(format="localized")
    st.dataframe(
        table, hide_index=True, width="stretch", height=38 + 35 * n,
        column_config={
            "종가(원)": won, "등락률(%)": two, "시가총액(조원)": st.column_config.NumberColumn(format="%.1f"),
            "PER": two, "업종 PER": two, "PBR": two, "업종 PBR": two, "EPS(원)": won, "업종 평균 EPS(원)": won,
        },
    )
    if fund_day:
        note = (f"사업분야와 PER·PBR·EPS는 {fund_day} 기준 최신 값입니다(네이버 금융). "
                "업종은 네이버 금융 업종 분류이고, 업종 평균은 같은 업종의 코스피 보통주로 계산합니다: "
                "업종 PER = 시가총액 합 ÷ 순이익 합, 업종 PBR = 시가총액 합 ÷ 순자산 합, 업종 평균 EPS = 단순평균. "
                "적자 종목은 PER이 비어 있고, 업종 순이익 합이 적자이면 업종 PER도 비어 있습니다. 주요 제품은 KIND 상장법인목록 기준입니다.")
        if abs((pd.Timestamp(fund_day) - day).days) > 7:
            note = f"**선택한 날짜({day:%Y-%m-%d}) 당시 값이 아닙니다.** " + note
        st.caption(note)
    else:
        st.caption("사업분야와 PER·PBR·EPS 데이터를 아직 받지 못했습니다. '데이터 새로 받기'를 눌러 주세요.")
    st.download_button("CSV 내려받기", table.to_csv(index=False).encode("utf-8-sig"),
                       f"kospi_top{n}_{day:%Y%m%d}.csv", "text/csv")
    if fund_day and abs((pd.Timestamp(fund_day) - day).days) <= 7:  # 분석은 최신 자료 기준이라 최근 날짜에서만 보여준다
        analysis_section(d)
    else:
        st.caption("종목별 분석(실적·전망·고평가 판단)은 최신 자료 기준이라 최근 거래일 화면에서만 표시합니다.")
    fig = go.Figure(go.Bar(
        x=d["조원"], y=d["Name"], orientation="h", marker_color=LINE,
        text=d["조원"].map("{:,.1f}".format), textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:,.1f}조원<extra></extra>",
    ))
    fig.update_layout(height=80 + 30 * n, margin=dict(l=0, r=50, t=10, b=0), xaxis_title="시가총액(조원)",
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")


def matrix(top: pd.DataFrame, days: pd.DatetimeIndex, fmt: str, caption: str) -> None:
    m = top[top["Date"].isin(days)].pivot(index="Rank", columns="Date", values="Name")
    m.columns = [c.strftime(fmt) for c in m.columns]
    m.index.name = "순위"
    st.caption(caption)
    st.dataframe(m, width="stretch", height=38 + 35 * len(m))


def page_top(basis: str, exclude_pref: bool, n: int) -> None:
    raw, warn = get_top()
    if warn:
        st.warning(warn)
    if raw.empty:
        st.error("시가총액 데이터가 없습니다. 인터넷 연결을 확인한 뒤 '데이터 새로 받기'를 눌러 주세요.")
        return
    top = mc.top_n(raw, n, exclude_pref)
    days = pd.DatetimeIndex(sorted(top["Date"].unique()))
    first, last = days.min(), days.max()
    st.title(f"코스피 시가총액 상위 {n}")
    st.caption(f"데이터 기간 {first:%Y-%m-%d} ~ {last:%Y-%m-%d} · 출처 한국거래소 전종목 시세(marcap 데이터셋)"
               + (" · 우선주 제외" if exclude_pref else " · 우선주 포함"))

    if basis == "일별":
        pick = st.date_input("날짜", last.date(), min_value=first.date(), max_value=last.date())
        day = mc.trading_day_on_or_before(days, pick)
        if day.date() != pick:
            st.info(f"{pick:%Y-%m-%d}은 휴장일이라 직전 거래일({day:%Y-%m-%d}) 기준으로 보여줍니다.")
        detail(top, day, f"{day:%Y년 %m월 %d일} 시가총액 상위 {n}")

    elif basis == "월별":
        ends = mc.period_end_dates(days, "M")
        years = sorted(ends.year.unique(), reverse=True)
        c1, c2 = st.columns(2)
        year = c1.selectbox("연도", years)
        in_year = ends[ends.year == year]
        month = c2.selectbox("월", list(in_year.month), index=len(in_year) - 1, format_func=lambda m: f"{m}월")
        day = in_year[in_year.month == month][0]
        detail(top, day, f"{year}년 {month}월 말 시가총액 상위 {n}" if day != last else f"{year}년 {month}월 시가총액 상위 {n} (최근 거래일)")
        st.subheader(f"{year}년 월별 순위 변화")
        matrix(top, in_year, "%m월", "각 월의 마지막 거래일 기준입니다.")

    else:
        ends = mc.period_end_dates(days, "Y")
        years = list(ends.year)
        lo, hi = st.select_slider("연도 범위", years, value=(max(years[0], years[-1] - 9), years[-1]))
        year = st.selectbox("자세히 볼 연도", [y for y in reversed(years) if lo <= y <= hi])
        day = ends[ends.year == year][0]
        detail(top, day, f"{year}년 말 시가총액 상위 {n}" if day != last else f"{year}년 시가총액 상위 {n} (최근 거래일)")
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
    page = st.radio("보기", ["시가총액 상위 종목", "코스피 지수"])
    basis = st.radio("기준", ["일별", "월별", "연도별"], horizontal=True)
    exclude_pref, top_count = False, 20
    if page == "시가총액 상위 종목":
        top_count = st.radio("순위 범위", [10, 20], index=1, horizontal=True, format_func=lambda v: f"상위 {v}")
        exclude_pref = st.checkbox("우선주 제외", help="삼성전자우 같은 우선주를 순위에서 뺍니다.")
    st.divider()
    if st.button("데이터 새로 받기"):
        st.cache_data.clear()
        for name, fn, unit in [("시가총액", mc.update_top, "거래일 추가"), ("코스피 지수", kidx.update_index, "거래일 추가"),
                             ("종목 지표", kfund.update_fundamentals, "종목"), ("실적·전망치", kearn.update_earnings, "종목")]:
            try:
                with st.spinner(f"{name} 받는 중…"):
                    st.success(f"{name}: {fn()[1]}{unit}")
            except Exception as e:
                st.error(f"{name} 실패: {e}")

if page == "시가총액 상위 종목":
    page_top(basis, exclude_pref, top_count)
else:
    page_index(basis)
