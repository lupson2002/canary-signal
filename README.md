# MQC-HAA 2x — 카나리아 앙상블 동적 레버리지

4대 거시경제 카나리아 지표로 위험 국면을 감지하고, 위험 점수에 따라 레버리지를 동적으로 조절하는
적응형 자산배분 전략. 매일 텔레그램 리포트 + Streamlit 대시보드(백테스트 결과) 제공.

## 전략
- **4대 카나리아** (위험 1점씩): TIP(통화), EEM(자본), HYG/IEF(신용), T10Y2Y(금리차)
- **13612W 모멘텀**: Score = 12·r1 + 4·r3 + 2·r6 + 1·r12
- **의사결정**: 위험 점수 ≥ 2 → Risk-Off. 0점 → 2배, 1점 → 1배
- **Risk-On**: 공격 8개(SPY/QQQ/IWM/EFA/EEM/VNQ/DBC/GLD) 중 2위 자산
- **Risk-Off**: 방어 3개(IEF/TLT/GLD) 1위 vs BIL 격차 ≥ 0.5 → 방어 1x, 아니면 현금 100%
- **백테스트 리밸런싱**: 월말 판정 → 다음 달 보유 (일간 모니터링과 달리 회전 비용을 현실화)

## 프로젝트 구조
- `config.py` — 티커/FRED/텔레그램/임계값 설정
- `data_fetcher.py` — yfinance + FinanceDataReader 수집
- `analyzer.py` — 13612W 모멘텀, 4지표 판정, 다수결 앙상블
- `backtest.py` — 백테스트 → `data/canary.db` 저장
- `main.py` + `notifier.py` — 매일 06:10 텔레그램 + json
- `dashboard_app.py` + `views/` — Streamlit 대시보드 (대시보드/현재포지션/전략설명)
- `current_signal.py` — 현재 신호 판정 (대시보드 포지션 페이지용)

## 실행
```bash
# 백테스트 + DB 생성
.venv/bin/python backtest.py

# 대시보드
.venv/bin/streamlit run dashboard_app.py

# 텔레그램 봇
.venv/bin/python main.py
```

## 대시보드 배포 (Streamlit Community Cloud)
- `requirements.txt`에 `streamlit`, `plotly` 포함
- `data/canary.db`는 백테스트 결과로 미리 생성해 커밋
- GitHub 저장소와 연동해 배포
