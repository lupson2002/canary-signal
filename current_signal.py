"""Current MQC-HAA 2x signal for the position page.

Reads the latest decision from data/canary.db (backtest_positions) so the dashboard
never re-downloads live data. Mirrors the backtest's monthly decision.
"""

import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "canary.db"

TICKER_KR = {
    "SPY": "S&P500", "QQQ": "나스닥", "IWM": "러셀2000", "EFA": "선진국",
    "EEM": "신흥국", "VNQ": "리츠", "DBC": "원자재", "GLD": "금",
    "IEF": "7-10년 국채", "TLT": "장기국채", "BIL": "현금",
}


def get_current_signal():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT decision_date, period_end, signal, asset, leverage, risk_score, "
        "canary_tip, canary_eem, canary_hygief, canary_t10y2y "
        "FROM backtest_positions ORDER BY decision_date DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        return None

    (decision_date, period_end, signal, asset, leverage, risk_score,
     canary_tip, canary_eem, canary_hygief, canary_t10y2y) = row

    return {
        "decision_date": decision_date,
        "period_end": period_end,
        "signal": signal,
        "asset": asset,
        "leverage": leverage,
        "risk_score": risk_score,
        "canaries": {
            "TIP": {"score": canary_tip, "risk": (canary_tip is None) or (canary_tip < 0)},
            "EEM": {"score": canary_eem, "risk": (canary_eem is None) or (canary_eem < 0)},
            "HYGIEF": {"score": canary_hygief, "risk": (canary_hygief is None) or (canary_hygief < 0)},
            "T10Y2Y": {"score": canary_t10y2y, "risk": (canary_t10y2y is None) or (canary_t10y2y < 0)},
        },
    }
