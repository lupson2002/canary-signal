"""데이터 수집 — yfinance(ALL_TICKERS 일간) + FinanceDataReader(FRED:T10Y2Y).

재시도(exponential backoff) + ffill/bfill 결측치 처리.
"""
from __future__ import annotations

import logging
import time

import FinanceDataReader as fdr
import pandas as pd
import yfinance as yf

from config import (
    ALL_TICKERS, BACKOFF_BASE, FRED_T10Y2Y, MAX_RETRIES,
    TICKER_HYG, TICKER_IEF, USER_AGENT,
)

log = logging.getLogger("mqc-fetcher")


def _retry(fn, label: str, max_retries: int = MAX_RETRIES):
    """Exponential backoff 재시도 래퍼."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_err = e
            wait = BACKOFF_BASE * (2 ** attempt)
            log.warning("[%s] 수집 실패(시도 %d/%d): %s — %.1fs 후 재시도", label, attempt + 1, max_retries, e, wait)
            time.sleep(wait)
    raise RuntimeError(f"[{label}] {max_retries}회 재시도 전부 실패: {last_err}")


def fetch_yf_prices(tickers: list[str] = None, start: str = "2022-01-01") -> pd.DataFrame:
    """yfinance 로 tickers 일간 종가 수집. 컬럼=티커, 인덱스=날짜."""
    tk = tickers or ALL_TICKERS
    def _dl():
        df = yf.download(" ".join(tk), start=start, interval="1d",
                         auto_adjust=True, progress=False, threads=True)
        if df is None or df.empty:
            raise RuntimeError("yfinance 빈 응답")
        if isinstance(df.columns, pd.MultiIndex):
            close = df["Close"] if "Close" in df.columns.levels[0] else df.xs("Close", level=0, axis=1)
        else:
            close = df
        return close.ffill().bfill()
    return _retry(_dl, "yfinance 일간")


def fetch_t10y2y() -> pd.Series:
    """FinanceDataReader 로 FRED:T10Y2Y (10년-2년 금리차, 일간, % 단위) 수집."""
    def _dl():
        s = fdr.DataReader(FRED_T10Y2Y, "2022-01-01")
        if s is None or s.empty:
            raise RuntimeError("FRED T10Y2Y 빈 응답")
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        return s.astype(float).ffill().bfill()
    return _retry(_dl, "FRED T10Y2Y")


def fetch_hyg_ief_ratio(prices: pd.DataFrame) -> pd.Series:
    """HYG/IEF 비율 시계열(신용스프레드 대용). 컬럼 누락 시 에러."""
    if TICKER_HYG not in prices.columns or TICKER_IEF not in prices.columns:
        raise RuntimeError("HYG/IEF 컬럼 누락")
    return (prices[TICKER_HYG] / prices[TICKER_IEF]).ffill().bfill()