#!/bin/sh
# Auto-deploy on the prod server (GitHub Actions is unavailable for this account). Cron runs it every minute
# (/etc/cron.d/homes-autodeploy); log: /var/log/homes-autodeploy.log.
# A new commit on origin/main → backend + bot tests in throwaway containers → deploy/deploy.sh (backup, pull, build, /health).
# A commit whose tests or deploy failed is not retried; push a fix (or delete /var/lib/homes-autodeploy.failed).
set -u
cd /opt/homes-in-georgia
git fetch -q origin main || exit 0
new=$(git rev-parse origin/main)
[ "$new" = "$(git rev-parse HEAD)" ] && exit 0
[ "$new" = "$(cat /var/lib/homes-autodeploy.failed 2>/dev/null)" ] && exit 0
echo "=== $(date -Is) $(git log --oneline -1 "$new" | cut -c1-100)"

src=/opt/homes-ci/src net=homes-ci
rm -rf $src && mkdir -p $src && git archive "$new" | tar -x -C $src
docker network create $net >/dev/null 2>&1
docker rm -f homes-ci-db >/dev/null 2>&1
docker run -d --rm --name homes-ci-db --network $net -e POSTGRES_USER=homes -e POSTGRES_PASSWORD=homes \
  -e POSTGRES_DB=homes_test pgvector/pgvector:pg16 >/dev/null
until docker exec homes-ci-db pg_isready -q -U homes -d homes_test; do sleep 1; done
# nice: the tests share the box with prod
nice -n 10 docker run --rm --network $net -v $src:/src -w /src -v homes-ci-pip:/root/.cache/pip \
  -e TEST_DATABASE_URL=postgresql+psycopg://homes:homes@homes-ci-db:5432/homes_test python:3.12-slim sh -c '
    pip install -q --root-user-action=ignore -r bot/requirements.txt &&
    (cd backend && python -m pytest -q -p no:cacheprovider) &&
    (cd bot && python -m unittest discover -s test) > /src/bot-tests.log 2>&1
    ' > /opt/homes-ci/tests.log 2>&1
ok=$?
docker rm -f homes-ci-db >/dev/null 2>&1
grep -E "passed|failed" /opt/homes-ci/tests.log | tail -5
grep -E "^(Ran|OK|FAILED)" $src/bot-tests.log 2>/dev/null; cp $src/bot-tests.log /opt/homes-ci/ 2>/dev/null
if [ $ok -ne 0 ]; then
  echo "tests FAILED, not deploying (full output: /opt/homes-ci/tests.log)"; echo "$new" > /var/lib/homes-autodeploy.failed; exit 1
fi
git show "$new":deploy/deploy.sh > /opt/homes-ci/deploy.sh && sh /opt/homes-ci/deploy.sh "$new" < /dev/null || { echo "$new" > /var/lib/homes-autodeploy.failed; exit 1; }
