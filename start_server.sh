#!/bin/bash
# 启动/重启股票分析 API 服务器 (端口 8765)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$SCRIPT_DIR/.server.pid"
LOGFILE="$SCRIPT_DIR/.server.log"
PORT=8765

# 杀掉占用端口的旧进程
OLD_PID=$(lsof -ti:$PORT 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    kill $OLD_PID 2>/dev/null
    sleep 1
fi

cd "$SCRIPT_DIR"
nohup python3 server.py > "$LOGFILE" 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PIDFILE"
sleep 2

if curl -s http://127.0.0.1:$PORT/api/health > /dev/null 2>&1; then
    echo "OK PID=$NEW_PID"
else
    echo "FAIL"
    cat "$LOGFILE"
    rm -f "$PIDFILE"
    exit 1
fi
