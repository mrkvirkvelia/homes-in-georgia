#!/bin/bash
# The `refresh` process (docs/ARCHITECTURE.md §1): refresh.sh now (REFRESH_ON_START=1, default) and every REFRESH_TICK_MIN
# (15); refresh.sh runs only the fetchers that are due by the admin's schedule. REFRESH_HOURS=0: run once and exit.
# Env as refresh.sh (PY, TG_FETCH, SKIP_FACEBOOK ...) + DATABASE_URL.
cd "$(dirname "$0")" || exit 1
export PYTHONUNBUFFERED=1   # fetcher output reaches `docker logs` at once, not lost in a buffer when a deploy kills it
rmdir data/refresh.lock 2>/dev/null   # a lock left by a killed run would block every future refresh
[ "${REFRESH_ON_START:-1}" = 1 ] && ./refresh.sh
[ "${REFRESH_HOURS:-}" = 0 ] && exit 0
while true; do
  sleep $(( ${REFRESH_TICK_MIN:-15} * 60 ))
  ./refresh.sh
done
