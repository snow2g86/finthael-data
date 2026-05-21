---
type: strategy
name: contra_volgate_demo
status: live
exchange: bybit
account: demo
updated: 2026-05-22
---

# contra_volgate_demo

## 한 줄 정의
Bybit demo perp 에서 변동성 게이트(volgate)에 잡힌 종목을 역방향(contra)으로 잡고
짧게 끊는 mean-revert 전략. Side 는 claude CLI AI 가 단독 결정 (2026-05-21~).

## 핵심 파라미터 (현재)
- **SL**: 3.0% (SL_MULT 1.5, CLAMP 3.0). A/B shadow: 1.0/1.5/2.0 동시 비교 중.
- **TP**: 1.0% (TP_MULT 0.5, CLAMP 2.5, MIN 0.3 = fee 0.075 + net 0.2). A/B shadow: 1.5/2.0/2.5.
- **R:R 운영값**: 0.33 (SL 3 / TP 1)
- **Fast SL**: held≥20min + max_pnl_pct<fee(0.075%) → 즉시 Taker close
- **Trailing**: trigger +0.3%(기본) / -0.1% offset. ZEC/BSB/HYPE 는 trigger 0.5% (slippage outlier 차단).
- **Trail BE Guard**: raw_pct≥0.075 미달 시 trail 발동 안 함 (fee level 미만 음수 trail 차단).
- **LONG sizing**: 2x_recover / conf_weight 적용 금지. notional 항상 $100. SHORT 만 amplify 허용.
- **Score gate**: AI 진입 전 score>=3 필수.
- **AI side decision**: BB_Z_STRONG/RSI_ALIGN default 필터 폐기. Claude Sonnet 4.6 단독 종합 판단.

## 인프라
- Demo Private WebSocket OMS (`bybit-private-ws.service`) 가 order/execution/position 실시간 sync.
- broker_sync 는 fallback.
- Zombie sweep guard: 70min+ open 안전망 + close_paper 110017 자동 orphan_close.

## 알려진 실패 모드
- LONG cohort 가 universe-wide 출혈 견인 (-$88 vs SHORT -$28). LONG 진입 시 보수적 sizing 유지.
- ZEC/BSB/HYPE slippage outlier (max 0.3%+ trail 손실). 별도 trail trigger.
- 5x leverage 운영이지만 monitor 의 "종목별 24h 신호 추세" PnL% 는 price_pct(레버리지 미포함). ROE 는 포지션 미니 리스트만.

## Do / Don't
- DO: SL/TP A/B shadow 결과를 정기 검토 (sl_ab_shadow / tp_ab_shadow 테이블).
- DO: claude CLI 호출 시 `-p --output-format json --max-turns 1 --allowed-tools ''` (도구 차단 우회 필수).
- DO: unrealized_pnl 컬럼은 manage_pos 의 max_pnl_pct UPDATE 시 동시 갱신.
- DON'T: LONG 에 2x_recover / conf_weight 적용 금지.
- DON'T: FLIP reason 을 UI/매트릭스/리포트에 노출 금지 (영구 폐기).
- DON'T: 격상 전 sim.db 데이터와 격상 후 paper.db 데이터 혼합 분석 금지 (다른 봇).

## 변경 이력 (최근)
- 2026-05-22: trading vault 와 연결, AI side decision 에 vault context 주입 검토 시작
- 2026-05-21: SL A/B shadow (1.0/1.5/2.0), AI solo 진입, score gate, trail BE guard, WS OMS, fast SL/trail tuning
- 2026-05-20: zombie guard, LONG no amplify, fast SL (A안), trail trigger 종목별 차등
- 2026-05-19: trailing stop 도입 (+0.2% trigger / -0.1% offset)
- 2026-05-18: SL_2_TP_1 → SL_3_TP_1 격상, RR 1:2.5 → R:R 0.33

## 관련
- [[../patterns]] (관련 패턴은 여기에 누적 예정)
