"""종목별 짧은 분석 문장을 규칙으로 만든다. 사람이 쓴 의견이 아니라 숫자를 정해진 기준에 대입한 결과다.

입력: fundamentals(종목 지표·업종 평균), earnings(분기 실적·컨센서스·목표주가·전망 공시)
출력: {코드: {"results": 실적 대 전망치, "guidance": 가이던스·전망, "fundamental": 펀더멘털, "verdict": 판단, "signals": [근거]}}
"""
from __future__ import annotations

import math

import pandas as pd

from kospi import fundamentals as kfund

GAP = 0.2  # 업종 평균 대비 ±20%를 벗어나면 신호로 본다
DISCLAIMER = ("이 분석은 공개 데이터를 정해진 기준에 대입해 자동으로 만든 참고 자료이며 투자 권유가 아닙니다. "
              "투자 판단과 책임은 본인에게 있습니다.")
CRITERIA = (f"판단 기준: ① PER이 업종 평균보다 {GAP:.0%} 이상 낮으면 저평가 신호, 높으면 고평가 신호 "
            f"② PBR도 같은 기준 ③ 증권사 평균 목표주가가 현재가보다 {GAP:.0%} 이상 높으면 저평가 신호, 현재가 이하면 고평가 신호. "
            "신호 합계가 저평가 쪽으로 2개 이상이면 '저평가 구간', 고평가 쪽으로 2개 이상이면 '고평가 구간', 그 외는 '중립', "
            "쓸 수 있는 신호가 2개 미만이면 '판단 보류'입니다.")


def ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def money(eok) -> str:
    """억원 → '12.3조원' / '4,567억원'"""
    if not ok(eok):
        return "자료 없음"
    if abs(eok) >= 1e4:
        return f"{eok / 1e4:,.1f}조원" if abs(eok) >= 1e6 else f"{eok / 1e4:,.2f}조원"
    return f"{eok:,.0f}억원"


def quarter_label(period: str) -> str:
    y, m = str(period).split(".")[:2]
    return f"{y}년 {(int(m) + 2) // 3}분기"


def change(new, old) -> str | None:
    """증감 표현. 적자가 끼면 비율 대신 전환 여부를 말한다."""
    if not ok(new) or not ok(old):
        return None
    if old <= 0 or new <= 0:
        if old <= 0 < new:
            return "흑자 전환"
        if new <= 0 < old:
            return "적자 전환"
        return "적자 지속" if new <= 0 else None
    return f"{(new / old - 1) * 100:+.1f}%"


def pct0(x: float, digits: int = 0) -> str:
    """부호 붙인 백분율. 반올림하면 0인 음수가 '-0%'로 찍히지 않게 한다."""
    return f"{round(x, digits + 2) + 0.0:+.{digits}%}"


def beat_word(pct: float) -> str:
    if pct >= 10:
        return "크게 웃돌았습니다(어닝 서프라이즈)"
    if pct >= 3:
        return "웃돌았습니다"
    if pct > -3:
        return "대체로 부합했습니다"
    if pct > -10:
        return "밑돌았습니다"
    return "크게 밑돌았습니다(어닝 쇼크)"


def actual_quarters(e: dict) -> list[dict]:
    """발표된 분기 실적. 분기 표에는 아직 전망치로 남아 있지만 잠정 실적이 나온 분기는 잠정치로 채운다."""
    qs = [q for q in e.get("quarters") or [] if not q.get("estimate") and ok(q.get("op"))]
    s = e.get("surprise")
    if s and ok(s.get("op_actual")) and (not qs or s["period"] > qs[-1]["period"]):
        qs = qs + [{"period": s["period"], "op": s["op_actual"], "estimate": False}]
    return qs


def results_text(e: dict) -> str:
    qs = actual_quarters(e)
    s, parts = e.get("surprise"), []
    if s and ok(s.get("op_actual")) and ok(s.get("op_consensus")):
        head = f"{quarter_label(s['period'])} 영업이익은 {money(s['op_actual'])}으로 시장 전망치({money(s['op_consensus'])})"
        if s["op_consensus"] > 0 and s["op_actual"] > 0:
            pct = (s["op_actual"] / s["op_consensus"] - 1) * 100
            parts.append(f"{head}를 {abs(pct):.1f}% {beat_word(pct)}." if abs(pct) >= 3 else f"{head}에 {beat_word(pct)}({pct0(pct / 100, 1)}).")
        else:
            if s["op_actual"] > 0:  # 적자가 끼면 비율 대신 흑자·적자 여부를 말한다
                parts.append(f"{head}의 적자 예상과 달리 흑자를 냈습니다.")
            elif s["op_consensus"] > 0:
                parts.append(f"{head}와 달리 적자를 냈습니다.")
            else:
                parts.append(f"{head}보다 적자 폭이 {'작았습니다' if s['op_actual'] > s['op_consensus'] else '컸습니다'}.")
        if ok(s.get("revenue_actual")) and ok(s.get("revenue_consensus")) and s["revenue_consensus"] > 0:
            parts.append(f"매출은 {money(s['revenue_actual'])}으로 전망치 대비 {pct0(s['revenue_actual'] / s['revenue_consensus'] - 1, 1)}입니다.")
        if s.get("preliminary"):
            parts.append("잠정 실적 기준입니다.")
    elif qs:
        parts.append(f"{quarter_label(qs[-1]['period'])} 영업이익은 {money(qs[-1]['op'])}입니다. 발표 직전 시장 전망치 자료가 없어 전망치와는 비교하지 못했습니다.")
    else:
        return "분기 실적 자료가 없습니다."
    if qs:
        last = qs[-1]
        yoy = next((q for q in qs if q["period"] == f"{int(last['period'][:4]) - 1}{last['period'][4:]}"), None)
        bits = []
        if len(qs) >= 2 and change(last["op"], qs[-2]["op"]):
            bits.append(f"전분기 대비 {change(last['op'], qs[-2]['op'])}")
        if yoy and change(last["op"], yoy["op"]):
            bits.append(f"전년 동기 대비 {change(last['op'], yoy['op'])}")
        if bits:
            parts.append(f"영업이익은 {', '.join(bits)}입니다.")
    return " ".join(parts)


def guidance_text(e: dict) -> str:
    parts = []
    g = e.get("guidance") or []
    if g:
        first, detail = g[0], ""
        summary = first.get("summary") or {}
        if summary.get("plan"):
            detail = f" 내용은 '{summary['plan']}'입니다."
        elif summary.get("years"):
            bits = [f"{y}년 " + ", ".join(f"{name} {money(v[k])}" for k, name in
                                         [("revenue", "매출"), ("op", "영업이익"), ("net", "순이익")] if ok(v.get(k)))
                    for y, v in sorted(summary["years"].items()) if any(ok(v.get(k)) for k in ("revenue", "op", "net"))]
            if bits:
                detail = f" 회사 전망은 {'; '.join(bits)}입니다."
        parts.append(f"회사가 최근 1년간 낸 전망·계획 공시는 {len(g)}건이며, 가장 최근은 {first['date']} '{first['title']}'입니다.{detail}")
    else:
        parts.append("회사가 공시한 정식 실적 가이던스는 확인되지 않았습니다.")
    act = actual_quarters(e)
    est = [q for q in e.get("quarters") or [] if q.get("estimate") and ok(q.get("op"))
           and (not act or q["period"] > act[-1]["period"])]
    if est:
        n = est[0]
        d = change(n["op"], act[-1]["op"]) if act else None
        parts.append(f"증권사 전망치 기준 {quarter_label(n['period'])} 영업이익은 {money(n['op'])}" + (f"으로 직전 분기 대비 {d}입니다." if d else "입니다."))
    an = e.get("annual") or []
    a_act = [a for a in an if not a.get("estimate") and ok(a.get("op"))]
    a_est = [a for a in an if a.get("estimate") and ok(a.get("op"))]
    if a_est:
        n = a_est[0]
        d = change(n["op"], a_act[-1]["op"]) if a_act else None
        parts.append(f"{str(n['period'])[:4]}년 연간 영업이익 전망치는 {money(n['op'])}" + (f"으로 전년 대비 {d}입니다." if d else "입니다."))
    if len(parts) == 1 and not g:
        parts.append("증권사 전망치도 제공되지 않습니다.")
    return " ".join(parts)


def fundamental(f: dict, sec: dict, e: dict) -> tuple[str, str, list[str]]:
    """(요약 문장, 판단, 근거 신호 목록)"""
    parts, signals, score, used = [], [], 0, 0
    for key, name in [("PER", "PER"), ("PBR", "PBR")]:
        v, s = f.get(key), sec.get(key)
        if ok(v) and ok(s) and s > 0 and v > 0:
            gap = v / s - 1
            parts.append(f"{name} {v:,.2f}배(업종 평균 {s:,.2f}배, {pct0(gap)})")
            used += 1
            if gap <= -GAP:
                score -= 1
                signals.append(f"{name}이 업종 평균보다 {abs(gap):.0%} 낮음(저평가 신호)")
            elif gap >= GAP:
                score += 1
                signals.append(f"{name}이 업종 평균보다 {gap:.0%} 높음(고평가 신호)")
        elif ok(v) and v > 0:
            parts.append(f"{name} {v:,.2f}배(업종 평균 없음)")
        elif key == "PER":
            parts.append("PER 없음(최근 4분기 적자)" if ok(f.get("EPS")) and f["EPS"] <= 0 else "PER 없음")
    if ok(f.get("EPS")) and ok(f.get("BPS")) and f["BPS"] > 0:
        parts.append(f"ROE 약 {f['EPS'] / f['BPS']:.1%}(EPS÷BPS)")
    text = ", ".join(parts) + "." if parts else "지표 자료가 없습니다."
    tp, close = e.get("target_price"), f.get("Close")
    if ok(tp) and ok(close) and close > 0:
        up = tp / close - 1
        n = e.get("analysts")
        text += f" 증권사 평균 목표주가는 {tp:,.0f}원으로 현재가({close:,.0f}원) 대비 {pct0(up)}입니다" + (f"({int(n)}곳)." if ok(n) else ".")
        used += 1
        if up >= GAP:
            score -= 1
            signals.append(f"목표주가가 현재가보다 {up:.0%} 높음(저평가 신호)")
        elif up <= 0:
            score += 1
            signals.append("목표주가가 현재가 이하(고평가 신호)")
    if used < 2:
        verdict = "판단 보류"
    elif score <= -2:
        verdict = "저평가 구간"
    elif score >= 2:
        verdict = "고평가 구간"
    else:
        verdict = "중립"
    return text, verdict, signals


def build_all(fund: pd.DataFrame, earnings: dict) -> dict:
    if fund.empty:
        return {}
    sectors = {r["Sector"]: r for r in kfund.sector_averages(fund).to_dict("records")}
    alias, stocks, out = earnings.get("alias") or {}, earnings.get("stocks") or {}, {}
    for f in fund.to_dict("records"):
        e = stocks.get(alias.get(f["Code"], f["Code"]))
        if e is None:
            continue
        if f["Code"] in alias:  # 우선주: 실적은 보통주와 같지만 목표주가는 보통주 것이라 쓰지 않는다
            e = {**e, "target_price": None}
        text, verdict, signals = fundamental(f, sectors.get(f["Sector"], {}), e)
        out[f["Code"]] = {"results": results_text(e), "guidance": guidance_text(e), "fundamental": text,
                          "verdict": verdict, "signals": signals}
    return out
