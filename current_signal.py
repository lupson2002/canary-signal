"""Current MQC-HAA 2x signal computation for the position page.

Recomputes the latest decision from live data (mirrors analyzer.py).
"""

import pandas as pd

from backtest import (
    ASSET_CASH, ASSET_DEFENSE_LIST, ASSET_OFFENSE_LIST, GAP_THRESHOLD,
    LEVERAGE_RISK_0, LEVERAGE_RISK_1, RISK_THRESHOLD, TICKER_EEM, TICKER_HYG,
    TICKER_IEF, TICKER_TIP, load_data, momentum_13612w,
)

TICKER_KR = {
    "SPY": "S&P500", "QQQ": "나스닥", "IWM": "러셀2000", "EFA": "선진국",
    "EEM": "신흥국", "VNQ": "리츠", "DBC": "원자재", "GLD": "금",
    "IEF": "7-10년 국채", "TLT": "장기국채", "BIL": "현금",
}


def get_current_signal():
    prices = load_data()
    hist = prices

    def _col(t: str) -> pd.Series:
        return hist[t] if t in hist.columns else pd.Series(dtype=float)

    m_tip = momentum_13612w(_col(TICKER_TIP))
    m_eem = momentum_13612w(_col(TICKER_EEM))
    if TICKER_HYG in hist.columns and TICKER_IEF in hist.columns:
        ratio = (hist[TICKER_HYG] / hist[TICKER_IEF]).ffill().bfill()
        m_hief = momentum_13612w(ratio)
    else:
        m_hief = None

    risk_tip = (m_tip is None) or (m_tip < 0)
    risk_eem = (m_eem is None) or (m_eem < 0)
    risk_hief = (m_hief is None) or (m_hief < 0)
    risk_score = int(risk_tip) + int(risk_eem) + int(risk_hief)
    is_risk_off = risk_score >= RISK_THRESHOLD

    canaries = {
        "TIP": {"score": m_tip, "risk": risk_tip},
        "EEM": {"score": m_eem, "risk": risk_eem},
        "HYGIEF": {"score": m_hief, "risk": risk_hief},
    }

    signal = asset = leverage = None
    rank2_asset = rank2_score = None
    defense_asset = defense_score = bil_score = gap = None

    if not is_risk_off:
        scores = {}
        for t in ASSET_OFFENSE_LIST:
            if t in hist.columns:
                sc = momentum_13612w(hist[t])
                if sc is not None:
                    scores[t] = sc
        if scores:
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            rank2_asset, rank2_score = ranked[1] if len(ranked) >= 2 else ranked[0]
        if rank2_score is not None and rank2_score > 0:
            if risk_score == 0:
                signal, leverage = "RISK-ON 2x", LEVERAGE_RISK_0
            else:
                signal, leverage = "RISK-ON 1x", LEVERAGE_RISK_1
            asset = rank2_asset
            is_risk_off = False
        else:
            is_risk_off = True

    if is_risk_off:
        defense_scores = {}
        for t in ASSET_DEFENSE_LIST:
            if t in hist.columns:
                sc = momentum_13612w(hist[t])
                if sc is not None:
                    defense_scores[t] = sc
        if ASSET_CASH in hist.columns:
            bil_score = momentum_13612w(hist[ASSET_CASH])
        if defense_scores:
            defense_asset, defense_score = max(defense_scores.items(), key=lambda x: x[1])
        if defense_score is not None and bil_score is not None:
            gap = defense_score - bil_score
        signal = "RISK-OFF 1x"
        leverage = 1.0
        if gap is not None and gap >= GAP_THRESHOLD:
            asset = defense_asset
        else:
            asset = ASSET_CASH

    return {
        "date": hist.index[-1].strftime("%Y-%m-%d"),
        "signal": signal,
        "asset": asset,
        "leverage": leverage,
        "risk_score": risk_score,
        "canaries": canaries,
        "rank2_asset": rank2_asset,
        "rank2_score": rank2_score,
        "defense_asset": defense_asset,
        "defense_score": defense_score,
        "bil_score": bil_score,
        "gap": gap,
    }
