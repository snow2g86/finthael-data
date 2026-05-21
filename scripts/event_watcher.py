#!/usr/bin/env python3
"""finthael trading vault — event watcher.

bybit_paper.db 의 contra_volgate_demo (strategy='whale_chase_contra_v1_volrev')
청산 이벤트를 폴링하여 다음 트리거에 inbox/ 에 AI draft 노트를 생성한다.

트리거:
- big_loss: 단일 거래 realized_pnl <= -30 USD
- streak_loss: 같은 종목 직전 3건 연속 손실 (이번 포함)

상태: /home/ai/trading-vault/.event_watcher.state.json  (last_seen_id)
cron: */10 * * * * (10분마다 폴링) — auto_sync 가 다음 cycle 에 push
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = "/home/ai/.openclaw/workspace/skills/coin-trading/data/bybit_paper.db"
STRATEGY = "whale_chase_contra_v1_volrev"
VAULT = Path("/home/ai/trading-vault")
STATE = VAULT / ".event_watcher.state.json"
LOG = VAULT / ".event_watcher.log"
CLAUDE = "/home/ai/.nvm/versions/node/v24.14.0/bin/claude"
MODEL = "claude-sonnet-4-6"
KST = timezone(timedelta(hours=9))

BIG_LOSS_THRESHOLD_USD = -30.0
STREAK_LEN = 3


def log(msg: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(KST).strftime('%F %T')}] {msg}\n")


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"last_seen_id": 0}


def save_state(s: dict):
    STATE.write_text(json.dumps(s, indent=2))


def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-").lower()[:40]


def fetch_new_closes(last_id: int) -> list[sqlite3.Row]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT id, symbol, side, entry_price, qty, leverage, status,
                  created_at, closed_at, close_reason, realized_pnl,
                  original_sl, max_pnl_pct, atr_pct
           FROM positions
           WHERE strategy=? AND closed_at IS NOT NULL AND id>?
           ORDER BY id ASC""",
        (STRATEGY, last_id),
    ).fetchall()
    con.close()
    return rows


def prior_n_closed_same_symbol(symbol: str, before_id: int, n: int) -> list[sqlite3.Row]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT id, side, close_reason, realized_pnl, closed_at
           FROM positions
           WHERE strategy=? AND symbol=? AND closed_at IS NOT NULL AND id<?
           ORDER BY id DESC LIMIT ?""",
        (STRATEGY, symbol, before_id, n),
    ).fetchall()
    con.close()
    return list(reversed(rows))


PROMPT = """당신은 알고리즘 트레이딩 학습 보조 분석가입니다. 아래 단일 손실 거래(또는 연속 손실)를
분석해 '교훈 draft' 마크다운을 작성하세요. 이 draft 는 사용자가 검토 후 patterns/ 폴더로
이동시킬 후보입니다.

전략: contra_volgate_demo (bybit demo perp, 변동성 게이트 종목을 역방향으로 mean-revert)
트리거: {trigger}
주요 이벤트: {event_line}

이번 거래 detail:
```json
{this_trade}
```

같은 종목 직전 거래 (오래된 → 최근):
```json
{prior_trades}
```

요구사항:
1. H2 4개 섹션: `관찰`, `해석 가설`, `검증 아이디어`, `잠정 액션`
2. 단정하지 말 것. "가설" / "추정" 으로 표기.
3. 길이 250-450 한국어 단어. 표 1개 이상.
4. 마지막에 한 줄: `> 이 노트는 AI draft 입니다 — 사용자 검토 후 분류/보강 필요.`
5. frontmatter 는 추가하지 말 것 (스크립트가 별도로 붙임).
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
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"claude rc={r.returncode} stderr={r.stderr[:300]}")
    data = json.loads(r.stdout)
    for k in ("result", "content", "text", "output"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list):
            chunks = [c.get("text", "") for c in v if isinstance(c, dict)]
            joined = "\n".join(t for t in chunks if t)
            if joined:
                return joined
    raise RuntimeError(f"missing body: keys={list(data.keys())}")


def iso_kst(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s


def trim_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    if "closed_at" in d:
        d["closed_kst"] = iso_kst(d.get("closed_at"))
    return d


def write_draft(trigger: str, row: sqlite3.Row, prior: list[sqlite3.Row]):
    closed_kst = datetime.fromisoformat(row["closed_at"]).replace(tzinfo=timezone.utc).astimezone(KST)
    fname = f"{closed_kst.strftime('%Y-%m-%d-%H%M')}-{trigger}-{slugify(row['symbol'])}-{row['id']}.md"
    out = VAULT / "inbox" / fname

    pnl = row["realized_pnl"] or 0
    if trigger == "big_loss":
        event_line = f"단일 거래 큰 손실 ({row['symbol']} {row['side']} pnl=${pnl:.2f})"
    elif trigger == "streak_loss":
        event_line = f"같은 종목 {STREAK_LEN}연속 손실 ({row['symbol']} {row['side']} 이번 pnl=${pnl:.2f})"
    else:
        event_line = trigger

    prompt = PROMPT.format(
        trigger=trigger,
        event_line=event_line,
        this_trade=json.dumps(trim_row(row), ensure_ascii=False, indent=2),
        prior_trades=json.dumps([trim_row(r) for r in prior], ensure_ascii=False, indent=2),
    )
    body = call_claude(prompt).strip()

    frontmatter = (
        f"---\n"
        f"type: inbox_draft\n"
        f"trigger: {trigger}\n"
        f"symbol: {row['symbol']}\n"
        f"side: {row['side']}\n"
        f"position_id: {row['id']}\n"
        f"realized_pnl: {row['realized_pnl']}\n"
        f"closed_kst: {closed_kst.strftime('%Y-%m-%d %H:%M')}\n"
        f"strategy: contra_volgate_demo\n"
        f"generated_by: claude-{MODEL}\n"
        f"generated_at: {datetime.now(KST).isoformat(timespec='seconds')}\n"
        f"---\n\n"
        f"# {trigger} — {row['symbol']} {row['side']} pos#{row['id']}\n\n"
    )

    out.write_text(frontmatter + body + "\n", encoding="utf-8")
    log(f"DRAFT_WROTE {out.name}")


def check_triggers(row: sqlite3.Row) -> list[tuple[str, list[sqlite3.Row]]]:
    triggers = []
    pnl = row["realized_pnl"] or 0
    if pnl <= BIG_LOSS_THRESHOLD_USD:
        triggers.append(("big_loss", []))

    # streak_loss: 이번 거래가 손실이고, 직전 (STREAK_LEN-1) 건도 모두 손실
    if pnl < 0:
        prior = prior_n_closed_same_symbol(row["symbol"], row["id"], STREAK_LEN - 1)
        if len(prior) == STREAK_LEN - 1 and all((p["realized_pnl"] or 0) < 0 for p in prior):
            triggers.append(("streak_loss", prior + [row]))

    return triggers


def main():
    state = load_state()
    last_id = state.get("last_seen_id", 0)

    # 첫 가동 안전망: 너무 옛날 거래까지 모두 처리하지 않도록 max(id) 로 점프
    if last_id == 0:
        con = sqlite3.connect(DB)
        max_id = con.execute(
            "SELECT COALESCE(MAX(id),0) FROM positions WHERE strategy=?",
            (STRATEGY,),
        ).fetchone()[0]
        con.close()
        state["last_seen_id"] = max_id
        save_state(state)
        log(f"SEED last_seen_id={max_id} (first run; skipping historical)")
        return

    rows = fetch_new_closes(last_id)
    if not rows:
        return

    processed_count = 0
    for r in rows:
        try:
            triggers = check_triggers(r)
            for tname, prior_or_chain in triggers:
                try:
                    if tname == "big_loss":
                        prior = prior_n_closed_same_symbol(r["symbol"], r["id"], 3)
                        write_draft(tname, r, prior)
                    elif tname == "streak_loss":
                        # chain 의 마지막이 r 임. 앞 두 건이 prior.
                        write_draft(tname, r, prior_or_chain[:-1])
                except Exception as e:
                    log(f"DRAFT_ERR id={r['id']} trigger={tname}: {e}")
            processed_count += 1
        except Exception as e:
            log(f"ROW_ERR id={r['id']}: {e}")
        state["last_seen_id"] = r["id"]

    save_state(state)
    if processed_count:
        log(f"PROCESSED n={processed_count} last_id={state['last_seen_id']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
