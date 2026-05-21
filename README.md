# finthael trading vault

AI 트레이딩 봇의 학습 자산을 마크다운으로 누적하는 vault.

## 구조

| 폴더 | 용도 | 작성 주체 |
|---|---|---|
| `patterns/` | 재현되는 교훈/규칙 (예: "5x SL 1% 가드 필요 케이스") | 사람 + AI draft (inbox 경유) |
| `strategies/` | 전략별 누적 노트 (스펙·파라미터·실패 모드) | 사람 + AI |
| `symbols/` | 종목별 거동/주의사항 (선택적) | 사람 + AI |
| `weekly/` | 주간 자동 리포트 (`YYYY-Wnn.md`) | AI (cron) |
| `incidents/` | 큰 손실/이상 사건 회고 | 사람 + AI |
| `inbox/` | AI 자동 draft 임시 보관소 → 검토 후 분류/삭제 | AI |
| `scripts/` | vault 관리·생성용 스크립트 | 사람 |

## 작성 규칙
- 각 노트 상단에 frontmatter (date / type / tags / strategy / symbol)
- 사실/관찰과 의견을 분리: `## 관찰` / `## 해석` / `## 액션`
- 관련 노트는 `[[wiki-link]]` 로 연결
- 거래 원자료는 DB(`bybit_paper.db` 등)에 있다; vault 는 *해석된 지식* 만 저장
- inbox 의 AI draft 는 사용자 검토 후 적절한 폴더로 이동

## 동기화
- ai 서버 `/home/ai/trading-vault/` 가 진실
- vault 변경 시 1시간 cron 으로 git auto-commit & push
- 로컬은 git pull 후 Obsidian 으로 열람
- 충돌 가능성 최소화 위해 로컬 편집은 가능한 한 push 후 진행

## AI 봇 통합
- contra_volgate_demo 의 claude CLI side decision 호출 시
  `strategies/contra_volgate_demo.md` + `symbols/{SYM}.md`(있으면) + 최근 `patterns/` 3건을
  prompt context 로 주입 (토큰 예산 가드 있음)
