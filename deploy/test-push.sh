#!/bin/bash
# Put the CURRENT local code (whatever branch is checked out, with uncommitted changes) on the TEST server.
#   bash deploy/test-push.sh           # update the test CRM, data kept
#   bash deploy/test-push.sh --reset   # also wipe its database and start again from fresh demo data
# Docs: docs/TEST-SERVER.md. The working CRM (/opt/homes-in-georgia, admin.hge.ge) is never touched.
set -euo pipefail

SERVER="${HIG_TEST_SERVER:-root@91.99.162.108}"
KEY="${HIG_TEST_KEY:-$HOME/.ssh/apartflow_hetzner}"
DIR=/opt/hig-test/app
URL=https://hig-test.91-99-162-108.sslip.io
SSH=(ssh -i "$KEY" -o ConnectTimeout=15 "$SERVER")
RESET=0
[ "${1:-}" = "--reset" ] && RESET=1

cd "$(dirname "$0")/.."
BRANCH=$(git branch --show-current)
COMMIT=$(git rev-parse --short HEAD)
DIRTY=$([ -n "$(git status --porcelain)" ] && echo " + незакоммиченные правки" || true)
echo "→ Тестовый сервер: ветка $BRANCH ($COMMIT)$DIRTY"

# only project files: tracked + new ones not in .gitignore (never .env, real agency data, node_modules, media)
git ls-files -co --exclude-standard -z > /tmp/hig-test-files
"${SSH[@]}" "mkdir -p $DIR"
rsync -a --delete --from0 --files-from=/tmp/hig-test-files -e "ssh -i $KEY" \
  --filter='protect .env.test' --filter='protect .deployed' ./ "$SERVER:$DIR/"
rm -f /tmp/hig-test-files

"${SSH[@]}" "BRANCH='$BRANCH' COMMIT='$COMMIT' DIRTY='$DIRTY' RESET=$RESET URL='$URL' bash -s" <<'REMOTE'
set -euo pipefail
cd /opt/hig-test/app
if [ ! -f .env.test ]; then   # first run: own secrets, never the working CRM's
  umask 077
  cat > .env.test <<EOF
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
TEST_PASSWORD=$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 10)
PUBLIC_URL=$URL
BOT_TOKEN=0:test-server-no-telegram
BOT_USERNAME=test_no_bot
EOF
  echo "  создан .env.test (свои ключи и пароль)"
fi
C="docker compose -p hig-test -f deploy/docker-compose.test.yml --env-file .env.test"
if [ "$RESET" = 1 ]; then echo "  сброс базы"; $C down -v; fi
$C up -d --build 2>&1 | grep -vE '^ *(#|=>)' | tail -5
for i in $(seq 1 60); do curl -fs http://127.0.0.1:8100/health >/dev/null && break; sleep 2; done
curl -fs http://127.0.0.1:8100/health >/dev/null || { echo "API не поднялся:"; $C logs --tail 40 api; exit 1; }
$C exec -T api sh -c 'cd /app/backend && python -m app.test_accounts' </dev/null
echo "$BRANCH $COMMIT$DIRTY $(date '+%d.%m.%Y %H:%M')" > .deployed
echo
echo "✅ Готово: $URL"
echo "   Логины: irakli, david, nino, georgiy, levan · пароль: $(grep ^TEST_PASSWORD= .env.test | cut -d= -f2)"
REMOTE
