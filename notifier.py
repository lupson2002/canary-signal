"""MQC-HAA 2x 알림 — 텔레그램 한글 메시지 + CLI 대시보드 + latest_signal.json."""
from __future__ import annotations

import json
import logging

import requests

from config import GAP_THRESHOLD, SIGNAL_JSON, TELEGRAM_API, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from analyzer import MqcReport

log = logging.getLogger("mqc-notifier")


def _fmt_score(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:+.4f}"


def _fmt_pct(v: float | None) -> str:
    """FRED T10Y2Y는 이미 % 단위 — ×100 금지."""
    if v is None:
        return "N/A"
    return f"{v:+.2f}%"


def _canary_tag(c: dict) -> str:
    return f"{'🚨 위험' if c['risk'] else '정상'} ({_fmt_score(c['score']) if c['key'] != 'T10Y2Y' else _fmt_pct(c['score'])})"


def _risk_mode_label(risk_score: int) -> str:
    """위험 점수 → 레버리지 모드 한글 라벨."""
    if risk_score == 0:
        return "완전 상승장 - 2배 레버리지 모드"
    if risk_score == 1:
        return "주의 국면 - 1배 노멀 모드"
    return "위험 국면 - 안전자산 대피"


def _position_line(rep: MqcReport) -> str:
    """최종 포지션 한 줄."""
    if rep.signal == "RISK-ON 2x":
        return f"🎯 최종 권장 포지션: [RISK-ON 2x] {rep.asset} 2.0x 레버리지 보유"
    if rep.signal == "RISK-ON 1x":
        return f"🎯 최종 권장 포지션: [RISK-ON 1x] {rep.asset} 1.0x 노멀 보유"
    if rep.asset == "BIL":
        return f"🎯 최종 권장 포지션: [RISK-OFF 1x] BIL (현금 100%) 보유"
    return f"🎯 최종 권장 포지션: [RISK-OFF 1x] {rep.asset} 1.0x 보유"


def build_telegram_message(rep: MqcReport) -> str:
    """텔레그램 한글 메시지 — 카나리아 + 자산 모멘텀 진단 + 최종 포지션."""
    c = rep.canaries
    ts = rep.datetime.replace(" KST", "")
    lines = [
        "[🚨 MQC-HAA 동적 레버리지 스케일링 신호]",
        f"📅 일시: {ts}",
        "",
        "📊 카나리아 지표 상태:",
        f"• TIP (통화): {_canary_tag(c['TIP'])}",
        f"• EEM (자본): {_canary_tag(c['EEM'])}",
        f"• HYG/IEF (신용): {_canary_tag(c['HYGIEF'])}",
        f"• T10Y2Y (금리차): {_canary_tag(c['T10Y2Y'])}",
        f"📈 위험 점수: {rep.risk_score} / 4 점 ({_risk_mode_label(rep.risk_score)})",
        "",
        "🔍 자산군 모멘텀 진단:",
    ]
    if rep.signal in ("RISK-ON 2x", "RISK-ON 1x"):
        lines.append(f"• 공격 2위 자산: {rep.rank2_asset} (모멘텀: {_fmt_score(rep.rank2_score)})")
    else:
        lines.append(f"• 방어 1위 자산: {rep.defense_asset or 'N/A'} (모멘텀: {_fmt_score(rep.defense_score)}) vs BIL ({_fmt_score(rep.bil_score)}) → 격차: {_fmt_score(rep.gap)}")
    lines.append("")
    lines.append(_position_line(rep))
    return "\n".join(lines)


def render_dashboard(rep: MqcReport) -> str:
    """CLI 대시보드."""
    c = rep.canaries
    lines = [
        "=" * 55,
        "     MQC-HAA 2x (문턱값 격차 스위칭) 일간 모니터링",
        "=" * 55,
        f"[분석 일시] {rep.datetime}",
        "",
        "[4대 카나리아 지표]",
        f"1. TIP  (통화)  : {_fmt_score(c['TIP']['score'])} | {'[위험]' if c['TIP']['risk'] else '정상'} ({c['TIP']['points']}점)",
        f"2. EEM  (자본)  : {_fmt_score(c['EEM']['score'])} | {'[위험]' if c['EEM']['risk'] else '정상'} ({c['EEM']['points']}점)",
        f"3. HYG/IEF(신용): {_fmt_score(c['HYGIEF']['score'])} | {'[위험]' if c['HYGIEF']['risk'] else '정상'} ({c['HYGIEF']['points']}점)",
        f"4. T10Y2Y(금리차): {_fmt_pct(c['T10Y2Y']['score'])} | {'[위험]' if c['T10Y2Y']['risk'] else '정상'} ({c['T10Y2Y']['points']}점)",
        "",
        "-" * 55,
        f"- 위험 점수: {rep.risk_score} / 4 점",
    ]
    if rep.signal == "RISK-ON 2x":
        lines += [
            "",
            "[공격 자산 모멘텀]",
            f"- 2위 자산: {rep.rank2_asset} (모멘텀 {_fmt_score(rep.rank2_score)}) → 2.0x 레버리지",
        ]
    else:
        lines += [
            "",
            "[방어 자산 격차]",
            f"- 방어 1위: {rep.defense_asset or 'N/A'} ({_fmt_score(rep.defense_score)})",
            f"- BIL 현금: ({_fmt_score(rep.bil_score)})",
            f"- 격차(Gap): {_fmt_score(rep.gap)} (임계 {GAP_THRESHOLD:+.1f})",
        ]
    lines += [
        "",
        f"★ 최종 신호: [{rep.signal}] {rep.asset} {rep.leverage:.1f}x ({_risk_mode_label(rep.risk_score)})",
        "=" * 55,
    ]
    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    """Telegram Bot API sendMessage."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("TELEGRAM_BOT_TOKEN/CHAT_ID 미설정 — 스킵")
        return False
    url = TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)
    try:
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message,
                                        "disable_web_page_preview": True}, timeout=20)
        if resp.status_code == 200 and resp.json().get("ok"):
            log.info("Telegram 전송 성공 (chat_id=%s)", TELEGRAM_CHAT_ID)
            return True
        log.error("Telegram 전송 실패: %s %s", resp.status_code, resp.text[:200])
        return False
    except Exception as e:  # noqa: BLE001
        log.error("Telegram 전송 예외: %s", e)
        return False


def save_signal_json(rep: MqcReport) -> None:
    """latest_signal.json 구조화 저장."""
    data = {
        "datetime": rep.datetime,
        "risk_score": rep.risk_score,
        "signal_type": rep.signal,
        "target_asset": rep.asset,
        "leverage": rep.leverage,
        "rank2_info": rep.rank2_info,
        "defense_info": rep.defense_info,
        "canaries": rep.canaries,
    }
    SIGNAL_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("신호 저장: %s", SIGNAL_JSON)