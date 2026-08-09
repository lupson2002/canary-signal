"""Backtest the MQC-HAA 2x (카나리아 앙상블) strategy.

Mirrors the inflation_compass dashboard contract: computes daily returns, weights,
turnover, yearly, equity and positions, then persists them to data/canary.db so the
Streamlit dashboard only SELECTs from the db (never re-runs the simulation).

Strategy (from analyzer.py):
  Step1: 4 canaries (TIP/EEM/HYG-IEF ratio/T10Y2Y) -> risk_score (2/4 majority -> Risk-Off)
  Step2:
    Risk-On:  offense 8 assets 13612W rank -> rank2. rank2 momentum>0 -> RISK-ON
              (leverage 2.0x if risk_score==0, 1.0x if risk_score==1). else auto Risk-Off.
    Risk-Off: defense 3 (IEF/TLT/GLD) rank1 + BIL. gap = def1 - bil.
              gap >= 0.5 -> def1 1x, else BIL cash 100%.
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    ASSET_CASH, ASSET_DEFENSE_LIST, ASSET_OFFENSE_LIST,
    GAP_THRESHOLD, LEVERAGE_RISK_0, LEVERAGE_RISK_1,
    LOOKBACK, RISK_THRESHOLD, TICKER_EEM, TICKER_HYG, TICKER_IEF, TICKER_TIP,
    W_R1, W_R12, W_R3, W_R6,
)

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "canary.db"

TRANSACTION_COST_BP = 30  # 0.3% = 30bp, charged one-way on each unit of notional traded

START_DATE = "2010-01-01"
MIN_LEN = LOOKBACK["r12"] + 5

ALL_TICKERS = sorted(set(ASSET_OFFENSE_LIST + ASSET_DEFENSE_LIST + [ASSET_CASH, TICKER_TIP, TICKER_EEM, TICKER_HYG, TICKER_IEF]))


def momentum_13612w(series: pd.Series) -> float | None:
    """13612W momentum score. None if insufficient data / non-positive prices."""
    s = series.dropna()
    if len(s) < MIN_LEN:
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


def load_data(start_date=START_DATE):
    """Download daily closes for all tickers. Returns daily close DataFrame."""
    df = yf.download(ALL_TICKERS, start=start_date, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"] if "Close" in df.columns.levels[0] else df.xs(df.columns.levels[0][0], axis=1, level=0)
    else:
        close = df
    close = close.ffill().bfill()
    return close


def compute_decision(prices: pd.DataFrame, date_idx: int) -> dict:
    """Compute the MQC-HAA decision as of prices.iloc[:date_idx+1].

    Returns dict with signal, asset, leverage, risk_score, rank2, defense, gap.
    """
    hist = prices.iloc[: date_idx + 1]

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
        "signal": signal, "asset": asset, "leverage": leverage,
        "risk_score": risk_score, "rank2_asset": rank2_asset,
        "rank2_score": rank2_score, "defense_asset": defense_asset,
        "defense_score": defense_score, "bil_score": bil_score, "gap": gap,
    }


def build_positions(prices: pd.DataFrame):
    """Daily decision -> list of (decision_date, next_date, signal, asset, leverage)."""
    positions = []
    for i in range(MIN_LEN, len(prices) - 1):
        dec = compute_decision(prices, i)
        decision_date = prices.index[i]
        next_date = prices.index[i + 1]
        positions.append((decision_date, next_date, dec))
    return positions


def simulate(positions, prices):
    """Daily return path (1x notional, leverage applied to the held asset)."""
    returns = prices.pct_change()
    daily_ret = pd.Series(0.0, index=prices.index)
    for decision_date, next_date, dec in positions:
        asset = dec["asset"]
        lev = dec["leverage"]
        if asset in returns.columns:
            daily_ret.loc[next_date] = returns.loc[next_date, asset] * lev
    start = positions[0][0]
    end = positions[-1][1]
    return daily_ret.loc[start:end]


def compute_turnover(positions):
    turnover = []
    prev_asset = None
    for decision_date, next_date, dec in positions:
        asset = dec["asset"]
        t = 1.0 if asset != prev_asset else 0.0
        turnover.append((decision_date, t))
        prev_asset = asset
    return turnover


def apply_costs(daily_ret, positions, cost_bp):
    cost_rate = cost_bp / 10000
    adj = daily_ret.copy()
    for decision_date, t in compute_turnover(positions):
        if t == 0:
            continue
        trade_days = daily_ret.index[daily_ret.index > decision_date]
        if len(trade_days) == 0:
            continue
        first_day = trade_days[0]
        adj.loc[first_day] = (1 + adj.loc[first_day]) * (1 - t * cost_rate) - 1
    return adj


def perf_stats(daily_ret):
    equity = (1 + daily_ret).cumprod()
    n_years = len(daily_ret) / 252
    cagr = equity.iloc[-1] ** (1 / n_years) - 1
    vol = daily_ret.std() * np.sqrt(252)
    sharpe = (daily_ret.mean() * 252) / vol
    mdd = (equity / equity.cummax() - 1).min()
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "MaxDD": mdd, "End equity ($1 start)": equity.iloc[-1]}, equity


def yearly_returns(daily_ret):
    return daily_ret.groupby(daily_ret.index.year).apply(lambda r: (1 + r).prod() - 1)


def build_weights_df(positions, index):
    tickers = sorted(set(p[2]["asset"] for p in positions))
    weights_df = pd.DataFrame(0.0, index=index, columns=tickers)
    for decision_date, next_date, dec in positions:
        mask = (index > decision_date) & (index <= next_date)
        weights_df.loc[mask, dec["asset"]] = 1.0
    return weights_df


def main():
    prices = load_data()
    positions = build_positions(prices)

    strat_ret = simulate(positions, prices)
    strat_ret_net = apply_costs(strat_ret, positions, TRANSACTION_COST_BP)
    returns = prices.pct_change()
    bench_ret = returns["SPY"].loc[strat_ret.index]

    strat_stats, strat_equity = perf_stats(strat_ret)
    strat_net_stats, strat_net_equity = perf_stats(strat_ret_net)
    bench_stats, bench_equity = perf_stats(bench_ret)

    n_changes = sum(1 for _, t in compute_turnover(positions) if t > 0)
    print(f"Backtest period: {strat_ret.index.min().date()} ~ {strat_ret.index.max().date()} ({len(positions)} daily decisions, {n_changes} position changes)")

    header = f"{'metric':<24}{'Strategy (gross)':>18}{f'Strategy (net {TRANSACTION_COST_BP}bp)':>22}{'SPY B&H':>12}"
    print(header)
    for k in strat_stats:
        print(f"{k:<24}{strat_stats[k]:>18.3f}{strat_net_stats[k]:>22.3f}{bench_stats[k]:>12.3f}")

    strat_yearly = yearly_returns(strat_ret)
    bench_yearly = yearly_returns(bench_ret)
    excess_yearly = strat_yearly - bench_yearly
    print("\nYearly returns:")
    print(f"{'year':<8}{'Strategy':>12}{'SPY':>12}{'Excess':>12}")
    for y in strat_yearly.index:
        print(f"{y:<8}{strat_yearly[y] * 100:>11.1f}%{bench_yearly[y] * 100:>11.1f}%{excess_yearly[y] * 100:>11.1f}%")
    win_rate = (excess_yearly > 0).mean()
    print(f"\nYears beating SPY: {(excess_yearly > 0).sum()}/{len(excess_yearly)} ({win_rate * 100:.0f}%)")

    pos_df = pd.DataFrame(
        [(d, e, p["signal"], p["asset"], p["leverage"], p["risk_score"]) for d, e, p in positions],
        columns=["decision_date", "period_end", "signal", "asset", "leverage", "risk_score"],
    )
    equity_df = pd.DataFrame(
        {"strategy_equity": strat_equity, "strategy_equity_net": strat_net_equity, "spy_equity": bench_equity}
    )
    yearly_df = pd.DataFrame({"strategy": strat_yearly, "spy": bench_yearly, "excess": excess_yearly}).reset_index(names="year")
    weights_df = build_weights_df(positions, strat_ret.index)

    daily_ret_df = pd.DataFrame({"strategy_ret": strat_ret, "spy_ret": bench_ret})
    turnover_df = pd.DataFrame(compute_turnover(positions), columns=["decision_date", "turnover"])
    turnover_df = turnover_df[turnover_df["turnover"] > 0]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    pos_df.assign(decision_date=pos_df.decision_date.dt.strftime("%Y-%m-%d"), period_end=pos_df.period_end.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_positions", conn, if_exists="replace", index=False
    )
    equity_df.reset_index(names="date").assign(date=lambda d: d.date.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_equity", conn, if_exists="replace", index=False
    )
    yearly_df.to_sql("backtest_yearly", conn, if_exists="replace", index=False)
    weights_df.reset_index(names="date").assign(date=lambda d: d.date.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_weights", conn, if_exists="replace", index=False
    )
    daily_ret_df.reset_index(names="date").assign(date=lambda d: d.date.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_daily_returns", conn, if_exists="replace", index=False
    )
    turnover_df.assign(decision_date=turnover_df.decision_date.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_turnover_events", conn, if_exists="replace", index=False
    )
    conn.close()
    print("\nsaved backtest tables to db")


if __name__ == "__main__":
    main()
