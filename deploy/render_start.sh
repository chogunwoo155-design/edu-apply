#!/bin/sh
# Render 무료 플랜 데모의 시작 명령 (render.yaml의 dockerCommand)
# 무료 플랜에는 배포 전 명령·예약 작업이 없어서, 서버가 시작할 때 마이그레이션과 배치를 같이 한다.
set -e
python manage.py migrate --noinput
python manage.py seed_sample --demo-admin

# 서버는 15분 동안 접속이 없으면 잠들고, 다시 깰 때마다 여기부터 실행된다.
# run_daily_jobs는 멱등이라(같은 날 같은 안내는 한 번만) 여러 번 돌아도 중복 발송이 없다.
(sleep 10 && python manage.py run_daily_jobs) &

exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 --timeout 30 --graceful-timeout 20 --access-logfile -
