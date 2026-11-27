# AWS 배포 계획

> 이 문서는 계획입니다. 이 과제에서는 실제 AWS에 배포하지 않았습니다.
> 대신 운영과 같은 구성을 로컬에서 재현할 수 있도록 `Dockerfile` · `docker-compose.yml`을 넣었습니다.
> 이미지 빌드와 PostgreSQL 위 테스트는 GitHub Actions(`.github/workflows/ci.yml`)가 매 push마다 확인합니다.

## 1. 전제

- 신청은 모집 시기에 몰리고, 평소에는 적다 → **작게 시작해서 늘릴 수 있는 구성**
- 개인정보(이름·이메일·주소)를 다룬다 → DB는 사설망, 비밀값은 코드 밖, 접근 기록
- 배치(안내 메일·시트 내보내기)는 하루 한두 번 몇십 초 → **상시 서버가 필요 없다**
- 운영 인원이 적다 → 서버를 직접 패치하는 일을 줄인다 (관리형 서비스)

## 2. 구성

```
사용자 ──HTTPS──> CloudFront ──> ALB ──> ECS Fargate: web (gunicorn, 컨테이너 2개)
                                              │
                                              ├──> RDS PostgreSQL 17 (사설 서브넷)
                                              ├──> SES (메일 발송)
                                              └──> Secrets Manager (DB 비밀번호, SECRET_KEY, 구글 서비스 계정)

EventBridge Scheduler ── 매일 08:00 KST ──> ECS RunTask: batch (같은 이미지, `python manage.py run_daily_jobs`)
                                              └──> 결과는 DB의 JobRun 표 + CloudWatch Logs

GitHub Actions ── 테스트 통과 ──> ECR에 이미지 push ──> ECS 서비스 롤링 배포 (OIDC, 장기 키 없음)
```

| 역할 | 서비스 | 고른 이유 |
|---|---|---|
| 웹 | ECS Fargate | 서버 OS를 관리하지 않음. 컨테이너 수만 늘리면 모집 시기 트래픽 대응 |
| DB | RDS PostgreSQL | 자동 백업(7일)·시점 복구, 마이너 버전 자동 패치 |
| 정적 파일 | WhiteNoise + CloudFront | 별도 S3 버킷 없이 캐시. 파일 업로드가 생기면 S3 추가 |
| 배치 | EventBridge Scheduler → ECS RunTask | 하루 몇십 초 작업에 상시 워커를 두지 않음. 실패 시 재시도 정책 |
| 메일 | Amazon SES | Django SMTP 백엔드에 그대로 연결. 반송·수신 거부는 SNS로 받아 기록 |
| 비밀값 | Secrets Manager | 작업 정의에서 환경 변수로 주입. 코드·이미지에 비밀값 없음 |
| 모니터링 | CloudWatch | 5xx 비율, 응답 시간, 배치 실패 시 알림(SNS → 메일/슬랙) |

## 3. 배치 운영

- 배치는 **여러 번 돌려도 같은 결과**가 되게 만들었다. 같은 신청자에게 같은 종류 메일은 한 번만 간다(`NotificationLog`의 유니크 제약). 스케줄러가 재시도해도 중복 발송이 없다.
- 실행마다 `JobRun`에 시작·끝·처리 건수·실패 이유를 남기고, 관리 화면에서 본다.
- 이미 Airflow를 쓰는 팀이라면 같은 명령을 `BashOperator`(또는 `KubernetesPodOperator`)로 부르면 된다. 명령 자체가 스케줄러에 묶여 있지 않다.

## 4. 단계별 계획

| 단계 | 구성 | 언제 |
|---|---|---|
| 0 | EC2 한 대 + docker compose + cron (+ RDS) | 시연·내부 테스트. 가장 싸고 빠름 |
| 1 | 위 2절 구성 (Fargate 1~2개, RDS 단일 AZ) | 실제 모집 시작 |
| 2 | RDS Multi-AZ, Fargate 오토스케일링(CPU 60%), WAF | 동시 모집·외부 제휴로 트래픽이 커질 때 |

## 5. 보안 점검표

- [ ] DB는 사설 서브넷, 보안 그룹은 ECS 작업에서만 5432 허용
- [ ] `DJANGO_DEBUG=0`, `ALLOWED_HOSTS`·`CSRF_TRUSTED_ORIGINS` 지정, HTTPS 강제 (`manage.py check --deploy`는 CI에서 실행)
- [ ] 관리자 화면(`/admin/`, `/manage/`)은 WAF 규칙 또는 사내 IP로 제한, 관리자 계정 MFA
- [ ] 개인정보 보관 기간을 정하고, 지난 신청은 배치로 익명화 (예: 교육 종료 1년 후)
- [ ] RDS 스냅샷 암호화, 복구 훈련 분기 1회

## 6. 비용 (서울 리전, 1단계, 대략)

정확한 금액은 AWS 요금 계산기로 다시 확인해야 합니다. 큰 덩어리만 적으면:
ALB가 가장 큰 고정비이고, 그다음이 RDS 최소 인스턴스, Fargate 소형 작업 1~2개 순서입니다.
배치(하루 1회 수십 초)와 SES(월 수천 통)는 거의 0에 가깝습니다.
비용을 더 줄여야 하면 0단계(EC2 한 대)로 시작하고, 트래픽이 생기면 1단계로 옮깁니다. 이미지와 명령이 같아서 옮기는 비용이 작습니다.
