#!/bin/sh
# Prod deploy, run by deploy/autodeploy.sh after green tests (or by hand): backup → pull → build → health check.
# Stops if the checkout has local edits or unpushed commits (someone worked on the server: push them first).
set -eu
cd /opt/homes-in-georgia
git fetch -q origin main
if [ -n "$(git status --porcelain --untracked-files=no)" ] || [ -n "$(git log origin/main..HEAD --oneline)" ]; then
  echo "server checkout has local changes or unpushed commits, not deploying:"; git status -sb; exit 1
fi
C="docker compose -f deploy/docker-compose.yml -f deploy/server.yml --env-file .env"
mkdir -p /opt/homes-backups/predeploy
$C exec -T db pg_dump -U homes -Fc homes > /opt/homes-backups/predeploy/db-$(date +%F-%H%M).dump
ls -t /opt/homes-backups/predeploy/db-*.dump | tail -n +11 | xargs -r rm -f   # keep the last 10 (~60 MB each)
git merge -q --ff-only origin/main
GIT_COMMIT=$(git rev-parse --short HEAD) $C up -d --build
for i in $(seq 1 30); do
  curl -fsS -o /dev/null http://127.0.0.1:8000/health && { echo "deployed $(git log --oneline -1)"; exit 0; }
  sleep 5
done
echo "api /health did not answer in 150 s"; $C logs --tail=80 api; exit 1
