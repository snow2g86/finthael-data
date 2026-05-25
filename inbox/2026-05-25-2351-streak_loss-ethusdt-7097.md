---
type: inbox_draft
trigger: streak_loss
symbol: ETHUSDT
side: short
position_id: 7097
realized_pnl: -0.0182
closed_kst: 2026-05-25 23:51
strategy: contra_volgate_demo
generated_by: claude-claude-sonnet-4-6
generated_at: 2026-05-25T15:01:23+09:00
---

# streak_loss — ETHUSDT short pos#7097

## 관찰

2026-05-25 22:51 ~ 23:51 KST, 약 **1시간 내 ETHUSDT short 3연속 fast_sl** 발생.

| 거래 ID | 방향 | KST 종료 | 종료 사유 | 실현 PnL |
|--------|------|----------|---------|---------|
| 7085 | short | 22:51 | fast_sl | -0.2190 |
| 7091 | short | 23:19 | fast_sl | -0.2169 |
| 7097 | short | 23:51 | fast_sl | -0.0182 |

세 건 모두 **동일 방향(short), 동일 종료 사유(fast_sl)**. 재진입 간격은 약 28~32분으로 짧다. 마지막 거래(7097)는 max_pnl_pct가 +0.034% 기록 — 잠깐 수익 구간이 있었으나 최종 손절. `original_sl = 0.0`, `atr_pct = null`이 눈에 띈다.

---

## 해석 가설

**가설 A — 단방향 추세 구간에서 역방향 반복 진입**
contra_volgate는 변동성 급등 시 mean-revert를 기대하지만, 이 시간대 ETH가 **지속적인 상승 추세**에 있었을 가능성이 있다. 추세가 살아있는 동안 변동성 게이트가 반복 트리거되면 전략은 계속 short을 내고, 매번 fast_sl에 걸리는 패턴이 추정된다.

**가설 B — ATR 데이터 결측의 영향**
`atr_pct = null`은 포지션 진입 당시 ATR 계산 실패를 시사한다. ATR 기반 SL 조정이 비활성화된 상태에서 고정 fast_sl로만 관리됐다면, 정상 변동성 범위 내 가격 움직임에도 조기 손절이 발생했을 가능성이 추정된다.

**가설 C — 연속 재진입 간격 미흡**
28~32분 간격 재진입은 직전 손실 원인(추세 미해소)이 해소되지 않은 상태에서의 반복 진입으로 볼 수 있다. streak_loss 이후 쿨다운 로직이 없거나 짧다면 동일 조건에서 재진입이 반복될 수 있다.

---

## 검증 아이디어

- 해당 1시간 구간의 ETH 1분/5분봉 차트에서 **추세 지속 여부** 확인 (단순 고점 갱신 횟수, EMA 기울기)
- `atr_pct = null`이 해당 3건에만 국한되는지, 또는 다른 손실 거래에서도 반복되는지 DB 쿼리
- fast_sl 손절 거리와 당시 ATR을 비교해 **SL이 변동성 대비 너무 좁지 않은지** 확인
- 같은 날 동일 전략에서 수익 거래가 있었다면, 진입 시간대·추세 조건 비교

---

## 잠정 액션

1. **streak 쿨다운 강화(추정 우선순위 높음)**: 같은 종목 2연속 fast_sl 발생 시 최소 60~120분 재진입 차단 검토
2. **ATR null 처리 보강**: `atr_pct = null`이면 진입 자체를 보류하는 guard 조건 추가 여부 검토
3. **추세 필터 실험(가설 A 검증용)**: 진입 전 단기 EMA 방향성 확인 — contra 방향과 EMA 방향이 충돌하면 스킵하는 파라미터 실험

> 이 노트는 AI draft 입니다 — 사용자 검토 후 분류/보강 필요.
