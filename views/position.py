"""현재 포지션 페이지 — 최신 MQC-HAA 2x 신호 판정."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from current_signal import TICKER_KR, get_current_signal


def fmt_score(v):
    return "N/A" if v is None else f"{v:+.4f}"


def risk_mode_label(risk_score):
    if risk_score == 0:
        return "완전 상승장 - 2배 레버리지 모드"
    if risk_score == 1:
        return "주의 국면 - 1배 노멀 모드"
    return "위험 국면 - 안전자산 대피"


st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

st.markdown(
    """
    <style>
    .ic-pos-card { background:#f7f8f4; border:1px solid #e1e0d9; border-radius:10px; padding:18px 20px; }
    .ic-pos-title { font-size:15px; font-weight:600; color:#16191a; }
    .ic-pos-regime { font-size:13px; color:#52564d; margin:6px 0 10px; }
    .ic-pos-asset { font-size:22px; font-weight:700; color:#bb6b2c; }
    .ic-pos-note { font-size:12px; color:#898781; margin-top:10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

sig = get_current_signal()

st.title("현재 포지션")

asset_kr = TICKER_KR.get(sig["asset"], sig["asset"])
st.markdown(
    f"""
    <div class="ic-pos-card">
    <div class="ic-pos-title">📅 최신 신호 ({sig['date']})</div>
    <div class="ic-pos-regime">{sig['signal']} · {risk_mode_label(sig['risk_score'])}</div>
    <div class="ic-pos-asset">{asset_kr} ({sig['asset']}) {sig['leverage']:.1f}x</div>
    <div class="ic-pos-note">위험 점수 {sig['risk_score']} / 4 · 최신 데이터 기준</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")
st.markdown("#### 카나리아 지표 상태")
c = sig["canaries"]
st.markdown(
    f"""
    - **TIP (통화)**: {fmt_score(c['TIP']['score'])} → {'🚨 위험' if c['TIP']['risk'] else '정상'}
    - **EEM (자본)**: {fmt_score(c['EEM']['score'])} → {'🚨 위험' if c['EEM']['risk'] else '정상'}
    - **HYG/IEF (신용)**: {fmt_score(c['HYGIEF']['score'])} → {'🚨 위험' if c['HYGIEF']['risk'] else '정상'}
    """
)
st.caption("위험 점수 ≥ 2 → Risk-Off. 카나리아 3개(2/4 다수결의 축약) 기준.")

st.markdown("")
st.markdown("#### 자산군 모멘텀 진단")
if sig["signal"] in ("RISK-ON 2x", "RISK-ON 1x"):
    st.markdown(
        f"**공격 2위 자산**: {sig['rank2_asset']} ({TICKER_KR.get(sig['rank2_asset'], sig['rank2_asset'])}) "
        f"· 모멘텀 {fmt_score(sig['rank2_score'])}"
    )
else:
    st.markdown(
        f"**방어 1위 자산**: {sig['defense_asset']} ({fmt_score(sig['defense_score'])}) "
        f"vs BIL ({fmt_score(sig['bil_score'])}) → 격차 {fmt_score(sig['gap'])}"
    )
