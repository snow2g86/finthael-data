#!/usr/bin/env bash
# 매주 일 22:00 KST cron 진입점
cd /home/ai/trading-vault || exit 1
LOG=/home/ai/trading-vault/.weekly.log
{
  echo "=== $(date '+%F %T') BEGIN weekly_report ==="
  /usr/bin/python3 /home/ai/trading-vault/scripts/weekly_report.py
  rc=$?
  echo "=== rc=$rc ==="
  if [ $rc -eq 0 ]; then
    /home/ai/trading-vault/scripts/auto_sync.sh
  fi
} >> "$LOG" 2>&1
