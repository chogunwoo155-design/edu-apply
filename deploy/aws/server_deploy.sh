#!/usr/bin/env bash
# EC2 안에서 실행: 최신 코드 받기 → 이미지 빌드 → 마이그레이션 → 웹 컨테이너 교체 → 배치 타이머 설치
# provision.sh가 SSM Run Command로 부른다. 서버에 SSH 키를 두지 않는다.
set -euo pipefail
APP=edu-apply
SRC=/opt/$APP
ENV_FILE=/etc/$APP.env
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/placement/region)

param() { aws ssm get-parameter --region "$REGION" --name "/$APP/$1" --with-decryption --query Parameter.Value --output text; }

cd "$SRC"
git fetch --quiet origin main
git reset --quiet --hard origin/main

PUBLIC_HOST=$(param public-host)
umask 077
cat > "$ENV_FILE" <<ENV
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=$(param secret-key)
DATABASE_URL=postgres://edu:$(param db-password)@$(param db-host):5432/edu_apply?sslmode=require
DJANGO_ALLOWED_HOSTS=$PUBLIC_HOST,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://$PUBLIC_HOST
DJANGO_PROXY_SSL_HEADER=HTTP_CLOUDFRONT_FORWARDED_PROTO
NUM_PROXIES=1
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEMO_NOTICE=1
DEMO_ADMIN_PASSWORD=$(param demo-admin-password)
ENV
umask 022

docker build --quiet -t $APP:latest . >/dev/null
docker run --rm --env-file "$ENV_FILE" $APP:latest python manage.py migrate --noinput
docker run --rm --env-file "$ENV_FILE" $APP:latest python manage.py seed_sample --demo-admin

docker rm -f $APP-web >/dev/null 2>&1 || true
docker run -d --name $APP-web --restart unless-stopped --env-file "$ENV_FILE" \
  --log-driver journald -p 80:8000 $APP:latest

# 매일 08:00(KST) 배치. 운영 계획(EventBridge Scheduler → ECS RunTask)의 작은 판
install -m 644 deploy/aws/edu-apply-batch.service /etc/systemd/system/
install -m 644 deploy/aws/edu-apply-batch.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now edu-apply-batch.timer

for i in $(seq 1 30); do
  if curl -fsS -o /dev/null http://127.0.0.1/healthz; then echo "배포 완료: https://$PUBLIC_HOST"; exit 0; fi
  sleep 2
done
echo "헬스 체크 실패" >&2
docker logs --tail 50 $APP-web >&2
exit 1
