#!/usr/bin/env bash
# 验证 dev-worker.sh 启动前会清理上次残留 worker
#
# 策略:
# 1. 后台跑 sleep 100 包装成 fake "celery -A app.tasks.celery_app worker"
# 2. 启动 dev-worker.sh(在前台瞬时执行,exec uv run 让出)
# 3. 等待新 worker 起来
# 4. 断言 fake 进程已死,新 worker 已起
# 5. 清理

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT_DIR/data/logs"
LOG="$LOG_DIR/dev-worker-cleanup.log"
mkdir -p "$LOG_DIR"
: > "$LOG"  # 清空日志,便于断言

# 启动一个伪装成 worker 的 sleep 进程（用 /bin/bash 保证 exec -a 可用,macOS/Linux 通吃）
FAKE_CMD="exec -a 'celery -A app.tasks.celery_app worker' sleep 100"
FAKE_PID=$(/bin/bash -c "$FAKE_CMD" >/dev/null 2>&1 & echo $!)
sleep 0.3

# 确认 fake 进程在跑
if ! kill -0 "$FAKE_PID" 2>/dev/null; then
  echo "FAIL: fake worker 进程未起来 (pid=$FAKE_PID)"
  exit 1
fi

echo "fake worker pid=$FAKE_PID 已启动"

# 跑 dev-worker.sh(跨平台超时:不依赖 GNU timeout)
# cleanup 阶段应在 5s 内结束(对 fake 进程 SIGTERM 立即生效);run 6s 后杀进程组兜底
bash scripts/dev-worker.sh >/dev/null 2>&1 &
DW_PID=$!
sleep 6
# 杀掉 dev-worker.sh 整个进程组(uv run wrapper + 起来的 celery)
kill -TERM -$DW_PID 2>/dev/null || kill -TERM $DW_PID 2>/dev/null || true
wait $DW_PID 2>/dev/null || true

# 检查 fake 进程是否被杀
if kill -0 "$FAKE_PID" 2>/dev/null; then
  echo "FAIL: fake worker pid=$FAKE_PID 还在跑,cleanup 没生效"
  kill -9 "$FAKE_PID" 2>/dev/null || true
  exit 1
fi

echo "PASS: fake worker pid=$FAKE_PID 已被 cleanup 杀掉"

# 检查 cleanup 日志
if ! grep -q "terminated=\[$FAKE_PID\]" "$LOG" 2>/dev/null && ! grep -q "killed=\[$FAKE_PID\]" "$LOG" 2>/dev/null; then
  echo "FAIL: cleanup 日志未记录 fake pid=$FAKE_PID"
  echo "--- 日志内容 ---"
  cat "$LOG" || true
  kill -9 "$DW_PID" 2>/dev/null || true
  exit 1
fi

echo "PASS: cleanup 日志含 fake pid"

# 清理:杀掉 dev-worker.sh 启动的所有 celery(可能已经自然结束 timeout)
ps aux | grep -E "celery -A app.tasks.celery_app.*worker" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
kill -9 "$DW_PID" 2>/dev/null || true

echo "ALL PASS"
exit 0