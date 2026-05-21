#!/usr/bin/env bash
# vault auto sync: pull → commit local changes → push
# 1시간 cron 으로 실행. 로그는 /home/ai/trading-vault/.sync.log
set -u
cd /home/ai/trading-vault || exit 1
log() { echo "[$(date '+%F %T')] $*" >> .sync.log; }

git pull --rebase --autostash origin main >> .sync.log 2>&1 || { log "PULL_FAIL"; exit 1; }

if [ -z "$(git status --porcelain)" ]; then
  log "NO_CHANGES"
  exit 0
fi

git add -A
msg="[auto] $(date '+%F %H:%M') updates"
git commit -m "$msg" >> .sync.log 2>&1 || { log "COMMIT_FAIL"; exit 1; }
git push origin HEAD >> .sync.log 2>&1 || { log "PUSH_FAIL"; exit 1; }
log "OK $(git rev-parse --short HEAD) $msg"
