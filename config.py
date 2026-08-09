"""MQC-HAA 2x (문턱값 격차 스위칭 동적 자산배분) 전역 설정."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# ── 공격 자산군 (8개) — Risk-On 시 2위(Rank 2) 선정 대상 ──────
ASSET_OFFENSE_LIST = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD"]

# ── 비현금 방어 자산군 (3개) — Risk-Off 시 1위 선정 대상 ──────
ASSET_DEFENSE_LIST = ["IEF", "TLT", "GLD"]

# ── 현금 방어 자산 ────────────────────────────────────────────
ASSET_CASH = "BIL"

# ── 4대 카나리아 지표 티커 ────────────────────────────────────
TICKER_TIP = "TIP"            # ① 실질 유동성
TICKER_EEM = "EEM"            # ② 신흥국 유동성
TICKER_HYG = "HYG"            # ③ 신용스프레드(하이일드)
TICKER_IEF = "IEF"            # ③ 신용스프레드(중기채)
FRED_T10Y2Y = "FRED:T10Y2Y"   # ④ 장단기 금리차

# ── 13612W 모멘텀 가중치 ─────────────────────────────────────
W_R1, W_R3, W_R6, W_R12 = 12, 4, 2, 1
LOOKBACK = {"r1": 21, "r3": 63, "r6": 126, "r12": 252}

# ── 의사결정 임계값 ───────────────────────────────────────────
RISK_THRESHOLD = 2      # 총 위험 >= 2 → Risk-Off
GAP_THRESHOLD = 0.5     # Score_Def1 - Score_BIL >= 0.5 → Def1 1x, < 0.5 → BIL

# ── 동적 레버리지 스케일링 ────────────────────────────────────
LEVERAGE_RISK_0 = 2.0   # 위험 0점(완전 상승장) → 2.0x
LEVERAGE_RISK_1 = 1.0   # 위험 1점(주의 국면) → 1.0x 노멀
# 위험 >=2점 → Risk-Off 1.0x (방어/현금)

# ── 텔레그램 ──────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# ── 수집 설정 ────────────────────────────────────────────────
MAX_RETRIES = 3
BACKOFF_BASE = 1.5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MQC-HAA/2.0"

# 수집 대상 티커(중복 제거) — 공격8 + 방어3 + BIL + 카나리아4
ALL_TICKERS = sorted(set(ASSET_OFFENSE_LIST + ASSET_DEFENSE_LIST +
                         [ASSET_CASH, TICKER_TIP, TICKER_EEM, TICKER_HYG, TICKER_IEF]))

PROJECT_DIR = Path(__file__).resolve().parent
SIGNAL_JSON = PROJECT_DIR / "latest_signal.json"
LOG_DIR = PROJECT_DIR / "logs"
DAILY_AT = "06:10"  # KST