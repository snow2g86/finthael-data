#!/usr/bin/env python3
"""finthael trading vault — weekly report generator.

contra_volgate_demo (strategy='whale_chase_contra_v1_volrev') 의 최근 7일
청산된 포지션을 집계 → claude CLI 에 분석을 맡겨 markdown 주간 리포트
를 weekly/YYYY-Wnn.md 로 저장.

cron: 매주 일요일 22:00 KST
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

DB = "/home/ai/.openclaw/workspace/skills/coin-trading/data/bybit_paper.db"
STRATEGY = "whale_chase_contra_v1_volrev"
VAULT = Path("/home/ai/trading-vault")
CLAUDE = "/home/ai/.nvm/versions/node/v24.14.0/bin/claude"
MODEL = "claude-sonnet-4-6"
KST = timezone(timedelta(hours=9))


def fetch_week_rows(end_utc: datetime) -> list[dict]:
    start_utc = end_utc - timedelta(days=7)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, symbol, side, entry_price, qty, leverage, status,
               created_at, closed_at, close_reason, realized_pnl,
               original_sl, max_pnl_pct, atr_pct
        FROM positions
        WHERE strategy=? AND closed_at IS NOT NULL
          AND closed_at >= ? AND closed_at < ?
        ORDER BY closed_at ASC
        """,
        (STRATEGY, start_utc.strftime("%Y-%m-%dT%H:%M:%S"),
         end_utc.strftime("%Y-%m-%dT%H:%M:%S")),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {"empty": True}
    pnls = [r["realized_pnl"] or 0.0 for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    by_side = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
    for r in rows:
        s = r["side"]
        pnl = r["realized_pnl"] or 0.0
        by_side[s]["n"] += 1
        by_side[s]["pnl"] += pnl
        if pnl > 0:
            by_side[s]["wins"] += 1
    for s in by_side:
        n = by_side[s]["n"]
        by_side[s]["wr"] = round(by_side[s]["wins"] / n * 100, 1) if n else 0
        by_side[s]["pnl"] = round(by_side[s]["pnl"], 2)

    by_reason = Counter(r["close_reason"] for r in rows)
    pnl_by_reason = defaultdict(float)
    for r in rows:
        pnl_by_reason[r["close_reason"]] += r["realized_pnl"] or 0.0
    reason_summary = [
        {"reason": k, "n": by_reason[k], "pnl": round(pnl_by_reason[k], 2)}
        for k in sorted(by_reason, key=lambda x: by_reason[x], reverse=True)
    ]

    by_sym = defaultdict(lambda: {"n": 0, "pnl": 0.0})
    for r in rows:
        by_sym[r["symbol"]]["n"] += 1
        by_sym[r["symbol"]]["pnl"] += r["realized_pnl"] or 0.0
    top_sym_pnl = sorted(
        [{"symbol": s, "n": v["n"], "pnl": round(v["pnl"], 2)}
         for s, v in by_sym.items()],
        key=lambda x: x["pnl"],
    )
    worst_syms = top_sym_pnl[:10]
    best_syms = list(reversed(top_sym_pnl[-10:]))

    top_wins = sorted(rows, key=lambda r: r["realized_pnl"] or 0, reverse=True)[:10]
    top_losses = sorted(rows, key=lambda r: r["realized_pnl"] or 0)[:10]

    def trim(r: dict) -> dict:
        return {
            "id": r["id"], "symbol": r["symbol"], "side": r["side"],
            "pnl": round(r["realized_pnl"] or 0, 4),
            "reason": r["close_reason"],
            "held_min": held_minutes(r),
            "max_pnl_pct": round((r["max_pnl_pct"] or 0) * 100, 3),
            "closed_kst": iso_to_kst(r["closed_at"]),
        }

    return {
        "empty": False,
        "n": len(rows),
        "pnl_sum": round(sum(pnls), 2),
        "wr": round(len(wins) / len(rows) * 100, 1),
        "win_n": len(wins),
        "loss_n": len(losses),
        "avg_pnl": round(mean(pnls), 4),
        "median_pnl": round(median(pnls), 4),
        "avg_win": round(mean(wins), 4) if wins else 0,
        "avg_loss": round(mean(losses), 4) if losses else 0,
        "by_side": dict(by_side),
        "by_reason": reason_summary,
        "best_symbols": best_syms,
        "worst_symbols": worst_syms,
        "top_wins": [trim(r) for r in top_wins],
        "top_losses": [trim(r) for r in top_losses],
    }


def iso_to_kst(s: str | None) -> str | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s


def held_minutes(r: dict) -> int | None:
    try:
        a = datetime.fromisoformat(r["created_at"])
        b = datetime.fromisoformat(r["closed_at"])
        return int((b - a).total_seconds() / 60)
    except Exception:
        return None


PROMPT_TEMPLATE = """당신은 알고리즘 트레이딩 시스템(bybit perp contra 전략)의 주간 리포트 작성 분석가입니다.
아래 집계 데이터를 보고 한국어로 마크다운 주간 리포트를 작성하세요.

전략: contra_volgate_demo (bybit demo perp, 변동성 게이트 종목을 역방향으로 진입하는 mean-revert 전략)
주차: {week_label}  (KST 기준 {start_kst} ~ {end_kst})

집계 JSON (top_wins/top_losses 의 max_pnl_pct 는 진입 후 최대 미실현 % · pnl 은 USD 실현손익):
```json
{stats_json}
```

요구사항:
1. 다음 6개 섹션을 H2 로 작성: `요약`, `Side/사유 분해`, `종목별 분포`, `Top Wins`, `Top Losses`, `관찰·가설`
2. `요약` 에 PnL/WR/거래수/평균 보유시간 한 줄씩
3. `Side/사유 분해` 에 long vs short, close_reason 별 PnL · 거래수 표
4. `종목별 분포` 에 Best 5 / Worst 5 표
5. `Top Wins`, `Top Losses` 는 표 (symbol/side/pnl/reason/held/max%)
6. `관찰·가설` 에 실제 데이터에 근거한 패턴 3-5개와 다음 주 검증할 가설 2-3개
7. 추측은 명시적으로 "가설" 로 표기, 단정 금지
8. 출력은 마크다운 본문만 (frontmatter 는 추가하지 말 것 — 스크립트가 별도로 붙임)
"""


def call_claude(prompt: str) -> str:
    cmd = [CLAUDE, "-p", prompt,
           "--model", MODEL,
           "--output-format", "json",
           "--max-turns", "1",
           "--allowed-tools", ""]
    env = os.environ.copy()
    env.setdefault("HOME", "/home/ai")
    env.setdefault("USER", "ai")
    env.setdefault("PATH", "/home/ai/.nvm/versions/node/v24.14.0/bin:/usr/bin:/bin")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI exit={r.returncode} stderr={r.stderr[:500]}")
    data = json.loads(r.stdout)
    # claude -p --output-format json 응답에서 본문 추출
    for k in ("result", "content", "text", "output"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list):
            chunks = [c.get("text", "") for c in v if isinstance(c, dict)]
            joined = "\n".join(t for t in chunks if t)
            if joined:
                return joined
    raise RuntimeError(f"claude response missing body: keys={list(data.keys())}")


def main(target_sunday_kst: datetime | None = None):
    now_kst = datetime.now(KST)
    if target_sunday_kst is None:
        # 가장 최근 일요일 22:00 KST 로 정렬
        days_since_sun = (now_kst.weekday() - 6) % 7  # weekday: Mon=0 ... Sun=6
        sunday = (now_kst - timedelta(days=days_since_sun)).replace(
            hour=22, minute=0, second=0, microsecond=0)
        if sunday > now_kst:
            sunday -= timedelta(days=7)
    else:
        sunday = target_sunday_kst

    end_utc = sunday.astimezone(timezone.utc)
    rows = fetch_week_rows(end_utc)
    stats = aggregate(rows)

    iso_year, iso_week, _ = sunday.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"
    start_kst = (sunday - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    end_kst = sunday.strftime("%Y-%m-%d %H:%M")

    if stats.get("empty"):
        body = "## 요약\n\n해당 주차에 청산된 거래가 없습니다.\n"
    else:
        prompt = PROMPT_TEMPLATE.format(
            week_label=week_label,
            start_kst=start_kst, end_kst=end_kst,
            stats_json=json.dumps(stats, ensure_ascii=False, indent=2),
        )
        body = call_claude(prompt).strip()

    frontmatter = (
        f"---\n"
        f"type: weekly\n"
        f"week: {week_label}\n"
        f"period: {start_kst} ~ {end_kst}\n"
        f"strategy: contra_volgate_demo\n"
        f"n_trades: {stats.get('n', 0)}\n"
        f"pnl_sum_usd: {stats.get('pnl_sum', 0)}\n"
        f"wr_pct: {stats.get('wr', 0)}\n"
        f"generated_by: claude-{MODEL}\n"
        f"generated_at: {datetime.now(KST).isoformat(timespec='seconds')}\n"
        f"---\n\n"
        f"# Week {week_label} — contra_volgate_demo\n\n"
    )

    out = VAULT / "weekly" / f"{week_label}.md"
    out.write_text(frontmatter + body + "\n", encoding="utf-8")
    print(f"WROTE {out} ({len(body)} chars body)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"ERROR: {e}\n")
        sys.exit(1)
