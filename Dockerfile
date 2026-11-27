# 웹(gunicorn)과 배치(manage.py 명령)가 같은 이미지를 쓴다.
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# 정적 파일은 빌드 때 모은다 (WhiteNoise가 서빙)
# (빌드 때는 DB·메일에 붙지 않는다. 설정이 운영 필수값을 검사하므로 자리값만 넣는다)
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=0 DATABASE_URL=postgres://build@localhost/build     EMAIL_HOST=build.invalid python manage.py collectstatic --noinput

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--graceful-timeout", "20", "--access-logfile", "-"]
