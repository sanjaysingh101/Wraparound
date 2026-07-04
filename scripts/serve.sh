#!/usr/bin/env bash
# Launch the Wraparound backend as a detached, long-lived daemon.
#
# Unlike a dev-server manager, this survives editor/preview idle timeouts and terminal
# closes — essential because Gaussian Splat training runs for 1–2 hours and the training
# subprocess is a child of this backend. setsid + nohup fully detach it from the caller.
#
# Usage:
#   scripts/serve.sh start    # start (no-op if already running)
#   scripts/serve.sh stop     # stop the daemon
#   scripts/serve.sh status   # report status
#   scripts/serve.sh restart
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${WRAPAROUND_PORT:-7345}"
LOG_DIR="${WRAPAROUND_LOG_DIR:-$HOME/Library/Application Support/Wraparound/logs}"
PID_FILE="$LOG_DIR/backend.pid"
LOG_FILE="$LOG_DIR/backend.log"
PYTHON="backend/.venv/bin/python"
mkdir -p "$LOG_DIR"

is_running() {
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1
}

start() {
  if is_running; then
    echo "Backend already running on :$PORT"
    return 0
  fi
  echo "Starting backend daemon on :$PORT (logs: $LOG_FILE)"
  # Detach into a new session (start_new_session) so no parent — shell, preview
  # manager, editor — can reap it via SIGHUP/SIGTERM on their own exit. macOS has no
  # `setsid`, so we use Python's os.setsid-equivalent to fully orphan the server.
  WRAPAROUND_PORT="$PORT" "$PYTHON" - "$PYTHON" "$LOG_FILE" "$PID_FILE" <<'PYEOF'
import os, sys, subprocess
python, log_file, pid_file = sys.argv[1], sys.argv[2], sys.argv[3]
with open(log_file, "ab") as out:
    proc = subprocess.Popen(
        [python, "-m", "wraparound"],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        start_new_session=True,  # new session + process group: survives parent exit
        env=os.environ,
    )
open(pid_file, "w").write(str(proc.pid))
PYEOF
  # Wait for the health endpoint before returning.
  for _ in $(seq 1 60); do
    if curl -s "http://127.0.0.1:$PORT/api/system/health" | grep -q '"ok":true'; then
      echo "Backend healthy (pid $(cat "$PID_FILE"))"
      return 0
    fi
    sleep 0.5
  done
  echo "Backend did not become healthy in time — check $LOG_FILE" >&2
  return 1
}

stop() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
  fi
  # Also clear anything still bound to the port.
  local pids
  pids=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
  [ -n "$pids" ] && kill $pids 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "Backend stopped"
}

status() {
  if is_running; then
    echo "running on :$PORT"
  else
    echo "not running"
  fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
