"""MQC-HAA 2x 시스템 — 일간 모니터링 엔트리포인트.

매일 06:10 KST — 데이터 수집 → 카나리아 + 자산 모멘텀 분석 → 텔레그램 + json.
"""
from __future__ import annotations

import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler

import schedule

from analyzer import analyze
from config import DAILY_AT, LOG_DIR
from data_fetcher import fetch_hyg_ief_ratio, fetch_t10y2y, fetch_yf_prices
from notifier import build_telegram_message, render_dashboard, save_signal_json, send_telegram

# ── 로깅(자정 회전, 14일 보관) ───────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
_file_h = TimedRotatingFileHandler(LOG_DIR / "mqc.log", when="midnight", backupCount=14, encoding="utf-8")
_file_h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[_file_h, logging.StreamHandler()])
log = logging.getLogger("mqc-main")


def job() -> None:
    """매일 06:10 — MQC-HAA 2x 분석."""
    try:
        log.info("=== MQC-HAA 2x 분석 시작 ===")
        prices = fetch_yf_prices()       # ALL_TICKERS (공격8+방어3+BIL+카나리아4)
        t10y2y = fetch_t10y2y()          # FRED T10Y2Y
        try:
            ratio = fetch_hyg_ief_ratio(prices)  # HYG/IEF 비율
        except Exception as e:  # noqa: BLE001
            log.warning("HYG/IEF 비율 산출 실패(%s) — ratio=None, fail-closed 처리", e)
            ratio = None
        rep = analyze(prices, t10y2y, ratio)

        dash = render_dashboard(rep)
        log.info("\n%s", dash)

        msg = build_telegram_message(rep)
        log.info("텔레그램 메시지:\n%s", msg)
        if send_telegram(msg):
            log.info("✓ 텔레그램 전송 완료 (%s %s %.1fx)", rep.signal, rep.asset, rep.leverage)
        else:
            log.warning("전송 스킵/실패 — 다음 날 재시도")

        save_signal_json(rep)
        log.info("=== 완료 (신호: %s %s %.1fx, 위험: %d/4) ===", rep.signal, rep.asset, rep.leverage, rep.risk_score)
    except Exception as e:  # noqa: BLE001
        log.exception("MQC-HAA 분석 실패: %s", e)


def main() -> None:
    schedule.every().day.at(DAILY_AT).do(job)
    log.info("MQC-HAA 2x 봇 시작 — 매일 %s KST. PID=%s", DAILY_AT, os.getpid())
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()