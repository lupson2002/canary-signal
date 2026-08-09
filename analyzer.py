"""MQC-HAA 2x 엔진 — 4대 카나리아 위험 판정(2/4 다수결) + 공격 2위/방어 격차 스위칭.

Step1: 4대 카나리아(2/4 다수결) → 총 위험 >=2 → Risk-Off
Step2:
  Risk-On:  공격 8개 13612W 순위 → 2위 자산. 모멘텀>0 → [RISK-ON 2x] {2위} 2.0x.
           2위 모멘텀<=0 → Risk-Off 자동 전환.
  Risk-Off: 방어 3(IEF/TLT/GLD) 1위(Def1)+Score. BIL Score.
           Gap = Score_Def1 - Score_BIL. >=0.5 → [RISK-OFF 1x] {Def1} 1.0x. <0.5 → BIL 현금 100%.

데이터 부족 시 fail-closed(위험 1점) — 리스크 감시 원칙.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta

import pandas as pd

from config import (
    ASSET_CASH, ASSET_DEFENSE_LIST, ASSET_OFFENSE_LIST,
    GAP_THRESHOLD, LEVERAGE_RISK_0, LEVERAGE_RISK_1,
    LOOKBACK, RISK_THRESHOLD,
    TICKER_EEM, TICKER_HYG, TICKER_IEF, TICKER_TIP,
    W_R1, W_R12, W_R3, W_R6,
)

log = logging.getLogger("mqc-analyzer")

KST = timezone(timedelta(hours=9))
MIN_LEN = LOOKBACK["r12"] + 5


def momentum_13612w(series: pd.Series) -> float | None:
    """13612W 모멘텀 스코어. 데이터 부족/0가격 시 None."""
    s = series.dropna()
    if len(s) < MIN_LEN:
        log.warning("데이터 부족(=%d < %d)", len(s), MIN_LEN)
        return None
    cur = float(s.iloc[-1])
    try:
        p1 = float(s.iloc[-1 - LOOKBACK["r1"]])
        p3 = float(s.iloc[-1 - LOOKBACK["r3"]])
        p6 = float(s.iloc[-1 - LOOKBACK["r6"]])
        p12 = float(s.iloc[-1 - LOOKBACK["r12"]])
    except IndexError:
        return None
    if any(p <= 0 for p in (p1, p3, p6, p12)):
        return None
    r1 = (cur / p1) - 1
    r3 = (cur / p3) - 1
    r6 = (cur / p6) - 1
    r12 = (cur / p12) - 1
    return W_R1 * r1 + W_R3 * r3 + W_R6 * r6 + W_R12 * r12


@dataclass
class CanaryInd:
    key: str
    name: str
    score: float | None
    risk: bool
    points: int


@dataclass
class MqcReport:
    datetime: str
    risk_score: int
    signal: str           # RISK-ON 2x / RISK-ON 1x / RISK-OFF 1x
    asset: str            # 최종 자산(티커 또는 BIL)
    leverage: float       # 2.0 / 1.0
    auto_switched: bool = False  # Risk-On→Off 자동 전환 여부
    rank2_asset: str | None = None
    rank2_score: float | None = None
    rank2_info: dict | None = None   # {ticker, score} — notifier/json용
    defense_asset: str | None = None
    defense_score: float | None = None
    bil_score: float | None = None
    gap: float | None = None
    defense_info: dict | None = None  # {def1_ticker, def1_score, bil_score, gap}
    canaries: dict | None = None


def analyze(prices: pd.DataFrame, t10y2y: pd.Series, ratio: pd.Series) -> MqcReport:
    """MQC-HAA 2x 분석."""
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    # ── Step1: 4대 카나리아 ─────────────────────────────
    def _col(t: str) -> pd.Series:
        return prices[t] if t in prices.columns else pd.Series(dtype=float)

    m_tip = momentum_13612w(_col(TICKER_TIP))
    m_eem = momentum_13612w(_col(TICKER_EEM))
    m_hief = momentum_13612w(ratio) if ratio is not None and not ratio.empty else None
    t10_last = float(t10y2y.iloc[-1]) if t10y2y is not None and len(t10y2y) > 0 else None

    # fail-closed: None → 위험 1점
    risk_tip = (m_tip is None) or (m_tip < 0)
    risk_eem = (m_eem is None) or (m_eem < 0)
    risk_hief = (m_hief is None) or (m_hief < 0)
    risk_t10 = (t10_last is None) or (t10_last < 0)

    canaries = {
        "TIP": CanaryInd("TIP", "통화", m_tip, risk_tip, int(risk_tip)),
        "EEM": CanaryInd("EEM", "자본", m_eem, risk_eem, int(risk_eem)),
        "HYGIEF": CanaryInd("HYGIEF", "신용", m_hief, risk_hief, int(risk_hief)),
        "T10Y2Y": CanaryInd("T10Y2Y", "금리차", t10_last, risk_t10, int(risk_t10)),
    }
    risk_score = sum(c.points for c in canaries.values())
    is_risk_off = risk_score >= RISK_THRESHOLD

    # ── Step2: 자산 선정 ──────────────────────────────────
    signal = asset = leverage = None  # M6: 사전 선언(정적 분석 대응)
    auto_switched = False              # H1: Risk-On→Off 자동 전환 플래그
    rank2_asset = rank2_score = None
    defense_asset = defense_score = bil_score = gap = None

    if not is_risk_off:
        # Risk-On: 공격 8개 13612W 순위 → 2위
        scores = {}
        for t in ASSET_OFFENSE_LIST:
            if t in prices.columns:
                sc = momentum_13612w(prices[t])
                if sc is not None:
                    scores[t] = sc
        if scores:
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            if len(ranked) >= 2:
                rank2_asset, rank2_score = ranked[1]
            else:
                rank2_asset, rank2_score = ranked[0]
        # 2위 모멘텀 >0 → RISK-ON (레버리지=위험점수별 차등). <=0 → Risk-Off 자동 전환
        if rank2_score is not None and rank2_score > 0:
            if risk_score == 0:
                signal = "RISK-ON 2x"
                leverage = LEVERAGE_RISK_0   # 2.0x
            else:  # risk_score == 1
                signal = "RISK-ON 1x"
                leverage = LEVERAGE_RISK_1   # 1.0x
            asset = rank2_asset
            is_risk_off = False
        else:
            is_risk_off = True
            auto_switched = True  # H1: 자동 전환 명시

    if is_risk_off:
        # Risk-Off: 방어 3(IEF/TLT/GLD) 1위 + BIL
        defense_scores = {}
        for t in ASSET_DEFENSE_LIST:
            if t in prices.columns:
                sc = momentum_13612w(prices[t])
                if sc is not None:
                    defense_scores[t] = sc
        if ASSET_CASH in prices.columns:
            bil_score = momentum_13612w(prices[ASSET_CASH])
        if defense_scores:
            defense_asset, defense_score = max(defense_scores.items(), key=lambda x: x[1])
        # Gap = Score_Def1 - Score_BIL
        if defense_score is not None and bil_score is not None:
            gap = defense_score - bil_score
        if gap is not None and gap >= GAP_THRESHOLD:
            signal = "RISK-OFF 1x"
            asset = defense_asset
            leverage = 1.0
        else:
            signal = "RISK-OFF 1x"
            asset = ASSET_CASH
            leverage = 1.0

    return MqcReport(
        datetime=now,
        risk_score=risk_score,
        signal=signal,
        asset=asset,
        leverage=leverage,
        rank2_asset=rank2_asset,
        rank2_score=rank2_score,
        rank2_info={"ticker": rank2_asset, "score": rank2_score} if rank2_asset else None,
        defense_asset=defense_asset,
        defense_score=defense_score,
        bil_score=bil_score,
        gap=gap,
        defense_info={
            "def1_ticker": defense_asset,
            "def1_score": defense_score,
            "bil_score": bil_score,
            "gap": gap,
        } if defense_asset else None,
        canaries={k: asdict(v) for k, v in canaries.items()},
    )