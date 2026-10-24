#!/usr/bin/env bash
# ============================================================
#  TalentFlow 前后端启动脚本（bash）
#  用法: ./start.sh [start|stop|restart|status|help]
#    start   启动前端(5173)+后端(8000)，后台运行，日志写 .run/*.log（默认）
#    stop    按 PID 文件 + 端口关闭服务
#    restart 先 stop 再 start
#    status  查看端口占用状态
#    help    显示帮助
#
#  Windows: 用 git bash / WSL 运行；.venv 解释器为 .venv/Scripts/python.exe
#  Linux/Mac: 将 PYEXE 改为 .venv/bin/python，ROOT 改为实际工程路径
# ============================================================

set -euo pipefail

ROOT="/e/program"                                  # git bash 路径；Linux/Mac 改为实际路径
FRONTEND="$ROOT/talent-flow"
BACKEND="$ROOT/talent-flow-backend"
PYEXE="$BACKEND/.venv/Scripts/python.exe"           # Windows；Linux/Mac 用 .venv/bin/python
RUNDIR="$BACKEND/.run"

mkdir -p "$RUNDIR"
cmd="${1:-start}"

# 按端口杀进程：Linux/Mac 用 lsof，Windows git bash 用 netstat+taskkill
kill_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti:"$port" 2>/dev/null | xargs -r kill 2>/dev/null || true
  elif command -v netstat >/dev/null 2>&1; then
    local pids
    pids=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $5}' | sort -u)
    for p in $pids; do taskkill -F -PID "$p" >/dev/null 2>&1 || true; done
  fi
}

# 按端口查状态
port_status() {
  local port="$1"
  local info="未监听"
  if command -v lsof >/dev/null 2>&1; then
    if lsof -ti:"$port" >/dev/null 2>&1; then info="LISTENING"; fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -ano 2>/dev/null | grep ":$port " | grep -q LISTENING; then info="LISTENING"; fi
  fi
  echo "  :$port $info"
}

case "$cmd" in
  start)
    echo "[启动] 前端 Vite (5173) + 后端 FastAPI (8000)"
    if [ ! -d "$FRONTEND/node_modules" ]; then
      echo "[前端] node_modules 不存在，先 npm install ..."
      ( cd "$FRONTEND" && npm install )
    fi
    if [ ! -x "$PYEXE" ]; then
      echo "[后端] 虚拟环境不存在: $PYEXE"
      echo "       请先: python -m venv .venv && .venv/Scripts/pip install -r requirements.txt"
      exit 1
    fi
    # 后端：后台运行，日志/PID 写入 .run
    nohup "$PYEXE" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload \
      > "$RUNDIR/backend.log" 2>&1 &
    echo $! > "$RUNDIR/backend.pid"
    # 前端：后台运行
    ( cd "$FRONTEND" && nohup npm run dev > "$RUNDIR/frontend.log" 2>&1 & echo $! > "$RUNDIR/frontend.pid" )
    echo "已启动。前端 http://localhost:5173 / 后端 http://localhost:8000/docs"
    echo "日志: $RUNDIR/backend.log, $RUNDIR/frontend.log"
    echo "关闭: ./start.sh stop"
    ;;

  stop)
    echo "[停止] 关闭前后端服务..."
    for f in backend frontend; do
      pf="$RUNDIR/$f.pid"
      if [ -f "$pf" ]; then
        pid=$(cat "$pf")
        if kill -0 "$pid" 2>/dev/null; then
          kill "$pid" 2>/dev/null || true
          echo "  $f (PID $pid) 已关闭"
        else
          echo "  $f (PID $pid) 未运行"
        fi
        rm -f "$pf"
      fi
    done
    # 兜底：按端口清理（reload worker、子进程等）
    kill_port 5173
    kill_port 8000
    ;;

  restart)
    "$0" stop
    sleep 1
    "$0" start
    ;;

  status)
    echo "[状态]"
    port_status 5173
    port_status 8000
    ;;

  help|--help|-h)
    echo "用法: ./start.sh [start|stop|restart|status|help]"
    echo "  start   启动前后端（默认）"
    echo "  stop    关闭前后端服务"
    echo "  restart 重启前后端"
    echo "  status  查看端口占用状态"
    echo "  help    显示本帮助"
    ;;

  *)
    echo "未知命令: $cmd"
    echo "用法: ./start.sh [start|stop|restart|status|help]"
    exit 1
    ;;
esac
