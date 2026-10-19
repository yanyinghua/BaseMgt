#!/usr/bin/env bash
# 管理本机开发用的私有 PostgreSQL 实例（数据目录 ~/pgdata，端口 5433）
# 用法: scripts/pg.sh start | stop | status | psql
set -e

PGBIN=${PGBIN:-/usr/lib/postgresql/14/bin}
PGDATA=${PGDATA:-$HOME/pgdata}
PORT=${PGPORT:-5433}
LOG=$PGDATA/server.log

case "$1" in
  start)
    if [ ! -f "$PGDATA/PG_VERSION" ]; then
      "$PGBIN/initdb" -D "$PGDATA" -U basemgt --auth=trust --encoding=UTF8 --locale=C
    fi
    "$PGBIN/pg_ctl" -D "$PGDATA" -o "-p $PORT -k /tmp -c listen_addresses=127.0.0.1" -l "$LOG" start
    "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PORT"
    ;;
  stop)
    "$PGBIN/pg_ctl" -D "$PGDATA" stop
    ;;
  status)
    "$PGBIN/pg_ctl" -D "$PGDATA" status
    ;;
  psql)
    shift || true
    "$PGBIN/psql" -h 127.0.0.1 -p "$PORT" -U basemgt -d "${1:-basemgt}"
    ;;
  *)
    echo "用法: $0 start | stop | status | psql [dbname]"
    exit 1
    ;;
esac
