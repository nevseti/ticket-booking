#!/usr/bin/env bash
# Нагрузочный тест на сервере (из каталога ~/ticket-booking, каталог loadtest рядом):
#
#   ./loadtest/run.sh rush [покупателей] [зрителей]   — старт продаж + проверка целостности
#   ./loadtest/run.sh read [запросов/с]               — чтение схемы: текущий режим api
#
# k6 работает контейнером в docker-сети проекта и ходит в api:8000 напрямую (мимо nginx:
# с одного IP его лимиты отсекли бы нагрузку — ADR 0008). Генератор нагрузки делит
# единственное ядро VPS с системой — цифры консервативные. Результаты: loadtest/results/.
set -euo pipefail

MODE=${1:?rush или read}
cd "$(dirname "$0")/.."
LT=$PWD/loadtest
RESULTS=$LT/results
DATA=$LT/data
mkdir -p "$RESULTS" "$DATA"
STAMP=$(date +%Y%m%d-%H%M%S)
NETWORK=$(docker network ls --format '{{.Name}}' | grep -m1 '^ticket-booking_default$')
K6_IMAGE=grafana/k6:2.3.0

compose() { docker compose "$@"; }
psql_() { compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' -- "$@"; }

# Уборка при любом выходе (в т. ч. при ошибке посреди прогона): тестовое мероприятие
# видно на публичной афише. Данные остаются, только если нарушен инвариант — для разбора.
KEEP_DATA=0
on_exit() {
  if [ "$KEEP_DATA" = 1 ]; then
    echo "Инвариант нарушен — данные теста оставлены для разбора: python -m scripts.loadtest cleanup" >&2
  else
    compose exec -T api python -m scripts.loadtest cleanup || true
  fi
}
trap on_exit EXIT

prepare() {
  compose exec -T api python -m scripts.loadtest prepare "$@" --out /tmp/loadtest-data.json
  compose cp api:/tmp/loadtest-data.json "$DATA/loadtest-data.json" >/dev/null
  EVENT_ID=$(python3 -c "import json;print(json.load(open('$DATA/loadtest-data.json'))['event_id'])")
}

k6_run() {
  local name=$1 script=$2
  shift 2
  # Пока идёт тест — снимок потребления ресурсов контейнерами раз в 10 с (сам docker
  # stats тоже стоит процессора, поэтому не чаще).
  (while :; do
     docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' | sed "s/^/$(date +%T),/"
     sleep 10
   done) > "$RESULTS/$STAMP-$name-stats.csv" &
  local stats_pid=$!
  # --user: k6 в образе работает под своим uid и не смог бы писать в loadtest/results.
  docker run --rm --network "$NETWORK" --memory 256m --user "$(id -u):$(id -g)" \
    -v "$LT:/scripts:ro" -v "$DATA:/data" -v "$RESULTS:/results" \
    -e K6_WEB_DASHBOARD=true -e K6_WEB_DASHBOARD_EXPORT="/results/$STAMP-$name-report.html" \
    "$@" "$K6_IMAGE" run --quiet --summary-export "/results/$STAMP-$name-summary.json" \
    "/scripts/$script" | tee "$RESULTS/$STAMP-$name-k6.txt" || true
  kill $stats_pid 2>/dev/null || true
}

wait_worker() {
  # Письма, уведомления и проекция схемы обрабатываются асинхронно — ждём, пока
  # воркер опубликует весь outbox.
  for _ in $(seq 1 60); do
    left=$(psql_ -tAc "SELECT count(*) FROM infra.outbox WHERE published_at IS NULL")
    [ "$left" = "0" ] && return
    sleep 2
  done
  echo "outbox не опустел за 2 минуты: $left событий" >&2
}

wait_sagas() {
  # Под перегрузкой клиент может бросить оплату по таймауту, и сага останется посередине
  # (деньги списаны, заказа ещё нет). Её доводит восстановление в воркере: раз в 60 с
  # берёт саги старше 120 с. Ждём, пока все саги придут в конечное состояние.
  local stuck
  stuck=$(psql_ -tAc "SELECT count(*) FROM orders.checkouts WHERE event_id = '$EVENT_ID' AND state IN ('started', 'paid')")
  echo "саг в промежуточном состоянии после теста: $stuck" | tee "$RESULTS/$STAMP-rush-sagas.txt"
  for _ in $(seq 1 60); do
    [ "$stuck" = "0" ] && break
    sleep 5
    stuck=$(psql_ -tAc "SELECT count(*) FROM orders.checkouts WHERE event_id = '$EVENT_ID' AND state IN ('started', 'paid')")
  done
  echo "после восстановления саг: $stuck в промежуточном состоянии" | tee -a "$RESULTS/$STAMP-rush-sagas.txt"
  # grep -c при нуле совпадений завершается с кодом 1 — при set -e это оборвало бы скрипт.
  runs=$(compose logs worker --since 10m 2>/dev/null | grep -c '"saga_recovery_done"' || true)
  echo "запусков восстановления, которые довели саги: $runs" | tee -a "$RESULTS/$STAMP-rush-sagas.txt"
}

case $MODE in
  rush)
    BUYERS=${2:-150}
    VIEWERS=${3:-50}
    prepare --users 3000
    k6_run rush sales_rush.js -e BUYERS="$BUYERS" -e VIEWERS="$VIEWERS"
    wait_worker
    wait_sagas
    wait_worker # восстановленные саги пишут свои события
    sleep 20 # уборщик удержаний (раз в 15 с) гасит брошенные удержания
    psql_ -v event="$EVENT_ID" < "$LT/verify.sql" | tee "$RESULTS/$STAMP-rush-verify.txt"
    if grep -qE '\| f$' "$RESULTS/$STAMP-rush-verify.txt"; then
      KEEP_DATA=1
      exit 1
    fi
    ;;
  read)
    RATE=${2:-150}
    READ_MODEL=$(compose exec -T api python -c "from app.core.config import settings; print(settings.seatmap_read_model)")
    prepare --users 10 --prefill 0.6
    # Первый запрос строит проекцию; в эксперименте меряем установившееся чтение.
    compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/events/$EVENT_ID/seatmap/status').read()"
    k6_run "read-$READ_MODEL-$RATE" seatmap_read.js -e RATE="$RATE"
    ;;
  *)
    echo "неизвестный режим: $MODE" >&2
    exit 1
    ;;
esac

echo "Результаты: $RESULTS/$STAMP-*"
