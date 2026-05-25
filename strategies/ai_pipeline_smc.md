# 전략: ai_pipeline_smc (Upbit KRW 현물, LONG 전용)

## 개요
업비트 KRW 현물 단타. 매시간 24h 등락률 양수 top5 를 후보로 잡고, 5분봉 마감마다 단기 추세가
상승인 종목만 SMC(Smart Money Concept) 관점으로 진입을 판단한다. 티어/승강 구조 없음.

## 파이프라인 (4 독립 서비스, DB로만 소통)
1. scanner — 매시간 24h signed_change_rate 양수 top5 → scan_candidates
2. analyzer — 5분봉 마감마다 활성 후보 중 1h 추세 상승(EMA20 slope>0 & close>EMA20)만
   → SMC 피처 요약 → Gemma 4 31b 1차 long/skip 판단 → analysis_signals(pending)
3. executor — pending 신호 → 사이징 → Sonnet 최종 컨펌 → 매수 → positions(open)
4. posmgr — positions(open) 청산 (포지션별 SL/TP + timeout + time_regime)

## 핵심 설계 — R:R 와 엣지 (중요)
- RR 약 2:1 (위험:보상). SL ~1.0% / TP ~0.5% (net, 유동성 따라 종목별 소폭 가변).
- **엣지는 per-trade R:R 이 아니라 높은 승률.** 손익분기 WR = 1.0/(0.5+1.0) ≈ 66.7%, 운영 목표 70%.
- **종목 퀴터 필터**: 종목별 청산 누적 n≥10 & 실현 WR<70% → 그 종목 거래 영구 제외.
  따라서 reward<risk 는 의도된 설계이며, R:R 만으로 진입을 거부하면 안 된다.
- 판단 기준은 "이 자리가 70%+ 승률을 유지할 고확률 long 인가" (추세 지속 / 눌림목 vs 추격 / 구조 / 유동성).

## 진입 (long only) — 돌파 OR 지지 구조
- 단기 추세 상승 필터 통과 필수 (1h EMA20 위 + slope>0).
- 유효 long 은 **구조적 근거**가 있을 때만:
  (A) **저항 돌파(BOS-up)**: 직전 저항(vs_res>0) 위로 거래량 동반 돌파·유지 → 추세지속 진입.
  (B) **지지 반등**: 지지/수요존으로 눌렸다(dip→sup≈0) bullish FVG/OB 동반 재탈환 → 눌림목 진입.
- 위 둘이 아니면 skip (중간에 떠 있음 / 거래량 없는 소진성 blow-off).
- **24h 큰 상승·높은 RSI 자체는 skip 사유 아님** — 거래량 동반 확실한 돌파면 유효 long.
- Gemma conf ≥ 0.55 통과 → Sonnet 최종 go/no-go.

## 사이징 (10/30/50K)
- 기본 10,000원.
- 종목 n≥10 & WR≥70% → 30,000원.
- 종목 n≥20 & WR≥80% & Gemma conf≥0.7 → 50,000원.

## 청산
- TP +0.5% / SL -1.0% (net, 포지션별 Gemma 값). 유동성 낮으면 SL 넓게.
- timeout_min(30~240) 초과 시 청산.
- 보유>120분 + 1h 레짐 약세(close<EMA20 & slope<0) → time_regime 청산.

## 교훈 (누적)
- (초기 — 데이터 쌓이면 업데이트)
