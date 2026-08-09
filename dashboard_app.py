"""Entry point for the MQC-HAA 2x (카나리아) Streamlit app.

Run with: streamlit run dashboard_app.py
"""

import streamlit as st

st.set_page_config(page_title="MQC-HAA 2x", layout="wide")

st.markdown(
    """
    <style>
    .ic-fixed-title {
        position: fixed; top: 0.85rem; left: 4rem; z-index: 1000000;
        font-size: 1.15rem; font-weight: 600; pointer-events: none;
    }
    </style>
    <div class="ic-fixed-title">MQC-HAA 2x</div>
    """,
    unsafe_allow_html=True,
)

pages = [
    st.Page("views/dashboard.py", title="대시보드", default=True),
    st.Page("views/position.py", title="현재 포지션"),
    st.Page("views/methodology.py", title="전략 설명"),
]
st.navigation(pages).run()
