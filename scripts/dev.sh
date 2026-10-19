#!/usr/bin/env bash
# 一键启动 BaseMgt 开发环境：后端 8000，前端 5173
# 用法: scripts/dev.sh [backend|frontend|all]
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)
MODE=${1:-all}

start_backend() {
  cd "$ROOT/backend"
  python3 manage.py migrate --noinput
  (nohup python3 manage.py runserver 127.0.0.1:8000 >/tmp/basemgt-backend.log 2>&1 &)
  echo "后端已启动: http://127.0.0.1:8000/api/health  (日志 /tmp/basemgt-backend.log)"
}

start_worker() {
  cd "$ROOT/backend"
  (nohup python3 manage.py run_worker --workers 2 --interval 2 >/tmp/basemgt-worker.log 2>&1 &)
  echo "worker 已启动（消费异步运行队列，日志 /tmp/basemgt-worker.log）"
}

start_frontend() {
  cd "$ROOT/frontend"
  [ -d node_modules ] || npm install
  (nohup npx vite --host 127.0.0.1 --port 5173 >/tmp/basemgt-frontend.log 2>&1 &)
  echo "前端已启动: http://127.0.0.1:5173  (日志 /tmp/basemgt-frontend.log)"
}

case "$MODE" in
  backend) start_backend ;;
  frontend) start_frontend ;;
  worker) start_worker ;;
  all) start_backend; start_worker; start_frontend ;;
  *) echo "用法: $0 [backend|worker|frontend|all]"; exit 1 ;;
esac
