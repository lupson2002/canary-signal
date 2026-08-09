"""Strategy description and calculation methodology - static reference page."""

import streamlit as st

st.markdown(
    """
    <style>
    div.block-container { padding-top: 2.6rem; }
    .ic-intro { font-size: 15px; color: #52564d; margin: 0 0 4px; line-height: 1.6; }
    .ic-body p, .ic-body ul { margin: 0 0 8px; font-size: 14px; line-height: 1.48; }
    .ic-body ul { padding-left: 20px; }
    .ic-body li { margin-bottom: 3px; }
    .ic-body h4 { font-size: 14px; margin: 10px 0 4px; font-weight: 700; color: #16191a; }
    .ic-body h4:first-child { margin-top: 0; }
    .ic-body code { font-size: 13px; background: #f2f3ee; padding: 1px 5px; border-radius: 3px; }
    .ic-body .formula { background: #f2f3ee; border-radius: 5px; padding: 8px 12px; font-size: 13px; margin: 4px 0 8px; line-height: 1.6; }
    </style>
    """,
    unsafe_allow_html=True,
)

tab_strategy, tab_signals, tab_cost = st.tabs(["전략설명", "신호", "매매비용"])

with tab_strategy:
    st.markdown(
        """
        <div class="ic-body">
        <ul>
        <li><b>MQC-HAA 2x</b> — 4대 거시경제 카나리아 지표로 위험 국면을 감지하고, 위험 점수에 따라
        레버리지를 동적으로 조절하는 적응형 자산배분 전략입니다.</li>
        <li>매일 판정해서 다음 거래일부터 보유합니다.</li>
        <li>위험 점수 0점 → 2배 레버리지, 1점 → 1배 노멀, 2점 이상 → 안전자산 대피.</li>
        </ul>
        <h4>자산군</h4>
        <ul>
        <li><b>공격 (8개)</b>: SPY, QQQ, IWM, EFA, EEM, VNQ, DBC, GLD — Risk-On 시 2위 자산 선정</li>
        <li><b>방어 (3개)</b>: IEF, TLT, GLD — Risk-Off 시 1위 자산 선정</li>
        <li><b>현금</b>: BIL — 격차가 작으면 현금 100%</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_signals:
    st.markdown(
        """
        <div class="ic-body">
        <h4>4대 카나리아 지표 (위험 1점씩)</h4>
        <ul>
        <li><b>TIP (통화)</b> — 실질 유동성. 13612W 모멘텀 &lt; 0</li>
        <li><b>EEM (자본)</b> — 신흥국 유동성. 13612W 모멘텀 &lt; 0</li>
        <li><b>HYG/IEF (신용)</b> — 신용스프레드 대용. 비율의 13612W 모멘텀 &lt; 0</li>
        <li><b>T10Y2Y (금리차)</b> — 장단기 금리차 최신값 &lt; 0 (역전)</li>
        </ul>
        <div class="formula">위험 점수 = 위험 카나리아 개수 · 총 위험 ≥ 2 → Risk-Off</div>

        <h4>13612W 모멘텀</h4>
        <div class="formula">Score = 12×r1 + 4×r3 + 2×r6 + 1×r12</div>
        <p>r1/r3/r6/r12 = 1/3/6/12개월 수익률. 데이터 부족 시 fail-closed(위험 1점).</p>

        <h4>Risk-On</h4>
        <p>공격 8개 자산의 13612W 순위에서 <b>2위</b> 자산을 선정합니다. 2위 모멘텀이 양수면
        위험 점수에 따라 2배(0점) 또는 1배(1점)로 보유합니다. 2위 모멘텀이 0 이하면 Risk-Off로 자동 전환합니다.</p>

        <h4>Risk-Off</h4>
        <p>방어 3개(IEF/TLT/GLD) 중 1위 자산과 BIL(현금)의 모멘텀 격차를 계산합니다.</p>
        <div class="formula">gap = Score_Def1 − Score_BIL · gap ≥ 0.5 → Def1 1x · gap &lt; 0.5 → BIL 현금 100%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_cost:
    st.markdown(
        """
        <div class="ic-body">
        <h4>매매비용 가정</h4>
        <p>매매비용은 턴오버 × 입력%로, 리밸런싱이 실제로 포지션을 바꾼 다음 거래일에만 적용됩니다
        (같은 포지션을 유지하는 날은 비용이 0).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
