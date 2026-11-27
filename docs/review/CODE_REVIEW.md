# 코드·운영 리뷰 (제3자 시선)

대상: 이 저장소 커밋 `64ffdc0` + 커밋 안 된 `Dockerfile`·`docker-compose.yml`·`.github/`·`docs/DEPLOY_AWS.md`
> 주의: 리뷰 도중 `automation/`(run_daily_jobs·mailer·sheets·models)과 `templates/emails/`가 새로 생겼다. 아직 `INSTALLED_APPS`에 없고 마이그레이션도 없어서 이 리뷰에서는 보지 않았다. 그 작업이 끝나면 1번·D1~D4·D7·G4를 다시 확인할 것.

확인 방법: `docs/review/scratch/test_review.py`, `test_review2.py`(pytest, 실제 PostgreSQL)로 직접 재현함. 재현 못 하고 코드만 읽고 판단한 것은 "짐작"으로 표시.

## 고칠 것 (값이 큰 차례)

1. **문서·compose가 없는 코드를 약속한다.** `docs/DEPLOY_AWS.md`에 `run_daily_jobs` 명령, `JobRun` 표, `NotificationLog` 유니크 제약, "여러 번 돌려도 중복 발송 없음"이라고 적혀 있지만 셋 다 코드에 없다. `docker compose --profile batch up batch`는 `Unknown command: 'run_daily_jobs'`로 바로 죽는다. 구글 시트 내보내기도 `gspread`만 requirements에 있고 코드가 없다. 면접관이 문서와 코드를 맞춰 보면 첫 번째로 걸린다.
2. **배치가 멱등이 아니다.** `send_contact_reminders`를 두 번 돌리면 3명에게 6통이 간다. 중간에 한 건 SMTP 오류가 나면 나머지는 안 보내고 예외로 끝난다(재시도하면 앞사람은 또 받는다). `--dry-run`·`--date`·발송 기록·로그가 없다. 직무가 "배치·자동화 개발"이라 이게 가장 중요하게 볼 곳이다.
3. **신청 API를 아무나 메일 발사기로 쓸 수 있다.** 인증·throttle·CAPTCHA 없이 POST마다 그 주소로 메일을 보낸다. 30번 요청하면 30통이 나간다. 남의 주소로 메일을 퍼붓거나 SES 평판을 떨어뜨릴 수 있다.
4. **메일을 요청 안에서 동기로 보내고, 실패하면 신청은 저장된 채 500을 낸다.** SMTP가 죽으면 행은 1건 저장되고 응답은 500 HTML이다. `apply.js`는 `res.json()`에서 터져서 "네트워크 오류"라고 보여 주니 사용자는 다시 누르고 중복 신청이 생긴다.
5. **중복 신청을 막지 않는다.** 같은 이메일·같은 교육으로 3번 넣으면 3건 저장, 접수 메일 3통. DB 제약도, 서비스 검사도 없다. 이메일도 대소문자를 정규화하지 않는다(`A@Example.COM` 그대로 저장).
6. **관리 화면 상태 변경이 입력을 검증하지 않는다.** `/manage/<pk>/status/`에 `status=hacked-value`를 보내면 302와 함께 그대로 저장된다. `status` 키가 없으면 500. DB에 `CheckConstraint`도 없어서 막아 줄 곳이 없다.
7. **신청 마감일·정원을 무시한다.** `apply_deadline`이 5일 지난 교육도 201. `capacity=1`인 교육에 3건 모두 201. 화면엔 "정원 24명", "신청 마감 ○월 ○일"이라고 보여 주면서 서버는 `is_open`만 본다.
8. **운영에서 메일 기본값이 콘솔이다.** `EMAIL_BACKEND` 환경 변수를 빠뜨리면 운영에서도 메일이 stdout(=CloudWatch 로그)으로만 가고 오류도 나지 않는다. 신청자 이름·이메일이 로그에 남고, 화면은 "메일을 보냈어요"라고 한다.
9. **"운영과 같은 구성"이라는 compose가 운영과 다르고 위험하다.** `DJANGO_DEBUG: "1"`이고, 웹이 뜰 때마다 `seed_sample --demo-admin`을 돌린다. 저장소에 비밀번호가 적힌 superuser `demo`가 생기고, 관리자가 고친 교육(마감 여부, 날짜, 커리큘럼)이 재시작 때마다 덮어써진다. 배포 계획 0단계가 "EC2 한 대 + docker compose"라서 그대로 인터넷에 열릴 수 있다.
10. **당일 연락 신청은 안내 메일을 영영 못 받고, 날짜 최소값이 시간대에 따라 바뀐다.** 서버는 오늘 날짜를 허용하는데, 배치는 하루 한 번 `contact_date=오늘`만 보니 배치 뒤에 들어온 당일 신청은 빠진다. `apply.js`는 `toISOString()`(UTC)으로 최소 날짜를 잡아서 KST 00~09시에는 오늘, 09시 이후에는 내일이 최소값이 된다.
11. **서비스 계층이 없다.** 신청 생성+메일은 `ApplicationViewSet.perform_create`, 상태 변경은 함수 뷰, 안내 메일은 관리 명령에 흩어져 있다. 메일 문구·발송 로직이 두 곳에 따로 있다. 공고가 "서비스 계층 설계"를 직접 언급하는데 보여 줄 게 없다.
12. **테스트가 API 6개뿐이다.** 배치, 관리 화면, 메일 실패, 마감·정원, 시간대 경계 테스트가 없다. 위 1~10번은 테스트가 하나도 잡지 못한다.

---

## 1. 정확성·검증

| 번호 | 심각도 | 어디 | 무엇이 잘못됐나 | 재현 방법 | 고침 안 |
|---|---|---|---|---|---|
| A1 | 큼 | `applications/views.py:36` | `request.POST["status"]`를 검증 없이 저장. 키가 없으면 KeyError 500 | staff로 `POST /manage/1/status/ status=hacked-value` → 302, DB에 `hacked-value`. 빈 POST → 500 | 폼 또는 `Status.values` 검사 후 400. 서비스 함수 `change_status()`로 옮기고 모델에 `CheckConstraint(status__in=...)` |
| A2 | 큼 | `applications/serializers.py:39-42` | `is_open`만 보고 `apply_deadline`·`capacity`는 안 봄 | 마감일을 5일 전으로 → 201. `capacity=1` → 3건 모두 201 | `validate()`에서 마감일(KST) 확인. 정원은 `select_for_update()`로 교육 행을 잠그고 셈 |
| A3 | 큼 | `serializers.py:34-37`, `send_contact_reminders.py:14` | 오늘 날짜 허용 + 배치는 하루 1회 `contact_date=today`만 → 배치 뒤 당일 신청은 안내 메일 없음 | 코드 읽음(로직상 확정). 오늘 날짜 POST → 201 확인 | 최소값을 내일로 통일하거나, 배치를 "아직 안 보낸 오늘 이하" 기준으로(발송 기록 필요) |
| A4 | 작음 | `static/js/apply.js:10-12` | `toISOString()`은 UTC. KST 00~09시는 min=오늘, 이후 min=내일. 서버 규칙(오늘 허용)과도 다름 | KST 08:30 → `2026-11-27`, 09:30 → `2026-11-28` (계산으로 확인) | 서버가 `min` 값을 템플릿에 내려 주기(`timezone.localdate()` 기준) |
| A5 | 작음 | `serializers.py:34` | 날짜 상한 없음 | `contact_date=9999-12-31` → 201 | 예: 오늘+90일 이내 |
| A6 | 작음 | `models.py:15,17`, `serializers.py:28` | 이름에 줄바꿈 허용, 우편번호 숫자 검사 없음(폼엔 칸도 없음) | `name="가\n나\r\n다"` → 201 그대로 저장. `postcode=abcde` → 201 | 제어문자 거부, `RegexValidator(r"^\d{5}$")` 또는 필드 제거 |
| A7 | 작음 | `serializers.py:45-68` | 관리자 PATCH는 날짜 검증이 없어 과거 날짜로 바꿀 수 있음, 이름 1글자 허용(생성과 규칙이 다름) | `PATCH contact_date=2000-01-01` → 200, `name="x"` → 200 | 공통 검증을 모델 `clean()`이나 서비스로 모으기 (과거 날짜 허용이 의도라면 문서에 적기) |
| A8 | 작음 | `static/js/apply.js:52` | 응답이 JSON이 아니면(500 HTML, 프록시 오류) "네트워크 오류"로 잘못 안내 | SMTP 실패 재현 시 응답 `text/html` 500 | `content-type` 확인 후 분기, 서버 500은 "접수됐을 수 있음" 안내 또는 서버를 고쳐 500 자체를 없앰 |

## 2. 보안·개인정보

| 번호 | 심각도 | 어디 | 무엇이 잘못됐나 | 재현 방법 | 고침 안 |
|---|---|---|---|---|---|
| B1 | 큼 | `config/settings.py:111-120`, `applications/api.py:17-20` | 익명 POST에 throttle 없음. 요청마다 임의 주소로 메일 발송 | 서로 다른 주소로 30번 POST → 모두 201, 메일 30통 | `AnonRateThrottle`(예: `10/hour`) + 같은 주소 하루 1통 제한, 필요하면 CAPTCHA/허니팟 |
| B2 | 큼 | `docker-compose.yml:19,24` | DEBUG=1, 매 기동마다 알려진 비밀번호 superuser 생성 | 코드 읽음 + `seed_sample.py:17`에 비밀번호 평문 | compose는 로컬 전용이라고 명시하거나 `--demo-admin`을 별도 profile로. 운영 구성은 DEBUG=0 |
| B3 | 큼 | `settings.py:122` | `EMAIL_BACKEND` 기본값이 콘솔. 운영에서 누락돼도 조용히 성공 → PII가 로그로 | `.env`에 값 빼고 신청 → `var_server.log`에 메일 본문이 그대로 찍힘 | `DEBUG=False`이면 SMTP 기본 + 필수값 없으면 기동 실패 |
| B4 | 작음 | `settings.py:131-134` | HSTS, `SECURE_SSL_REDIRECT` 없음 | `check --deploy` → W004, W008 | ALB에서 리다이렉트하더라도 `SECURE_HSTS_SECONDS` 설정, 아니면 이유를 적어 silence |
| B5 | 작음 | `settings.py:111` | 운영에서도 DRF Browsable API 노출 | 짐작(기본 렌더러) | 운영은 `JSONRenderer`만 |
| B6 | 작음 | `applications/views.py:32-38`, `admin.py` | 상태 변경 이력·누가 바꿨는지 기록 없음. 개인정보 접근 기록도 없음(배포 문서는 "접근 기록"을 전제로 함) | 코드 읽음 | `ApplicationStatusLog(application, from, to, by, at)` |

## 3. 데이터 무결성

| 번호 | 심각도 | 어디 | 무엇이 잘못됐나 | 재현 방법 | 고침 안 |
|---|---|---|---|---|---|
| C1 | 큼 | `applications/models.py:28-35` | 같은 사람·같은 교육 중복 허용, 이메일 정규화 없음 | 같은 payload 3번 → 3건, 메일 3통. `A@Example.COM` 그대로 저장 | 이메일 소문자 정규화 + `UniqueConstraint(Lower("email"), "course", name=...)` (취소 상태가 생기면 `condition=`) → 중복은 400으로 안내 |
| C2 | 큼 | `models.py:21-23` | 상태값 DB 제약 없음 (A1과 연결) | A1 참고 | `CheckConstraint` |
| C3 | 작음 | `courses/management/commands/seed_sample.py:105-106` | `update_or_create(defaults=전체)` + 커리큘럼 전체 삭제 → 실데이터 위에서 돌리면 관리자가 고친 내용이 사라짐. compose가 매 기동 실행 | 코드 읽음 | 없을 때만 만들기(`get_or_create`), 또는 `--reset` 옵션일 때만 덮어쓰기 |

## 4. 메일·배치

| 번호 | 심각도 | 어디 | 무엇이 잘못됐나 | 재현 방법 | 고침 안 |
|---|---|---|---|---|---|
| D1 | 막음 | `docker-compose.yml:35`, `docs/DEPLOY_AWS.md:23-24,41-42` | `run_daily_jobs`·`JobRun`·`NotificationLog` 없음. 문서의 멱등성 설명이 사실이 아님 | `manage.py run_daily_jobs` → Unknown command | 문서대로 구현하거나 문서를 현재 코드에 맞게 고치기. 둘 중 하나는 제출 전에 반드시 |
| D2 | 큼 | `send_contact_reminders.py:18-28` | 재실행 시 중복 발송, 발송 기록 없음 | 대상 3명, 2번 실행 → 6통 | `NotificationLog(application, kind, sent_on)` + `UniqueConstraint`. 보내기 전에 기록 행을 `get_or_create`로 선점 → 발송 → 결과 갱신 |
| D3 | 큼 | 같은 곳 | 한 건 실패하면 루프 전체가 예외로 끝남 | 2번째 발송에서 `ConnectionResetError` → 3번째는 안 감 | 건별 try/except, 실패 건수 집계, 실패가 있으면 종료 코드 1(스케줄러 알림용) |
| D4 | 큼 | 같은 곳 | `--dry-run`, `--date YYYY-MM-DD`(재처리), 처리 건수 로그, `logging` 사용 없음. `settings.py`에 `LOGGING` 없음 | `send_contact_reminders --help`에 옵션 없음 | 옵션 추가, `logger.info("sent=%d failed=%d skipped=%d")`, JSON 로그 |
| D5 | 큼 | `applications/api.py:34-44` | 요청 안에서 동기 SMTP. 실패 시 행은 남고 500 | `send_mail`을 실패하게 패치 → 500 `text/html`, 행 1건 | 서비스에서 `transaction.atomic()` + `transaction.on_commit()`로 발송, 실패는 로그만 남기고 201. 또는 발송 대기열(아웃박스 표) → 배치가 보냄 |
| D6 | 작음 | `send_contact_reminders.py:14` | `select_related("course")` 없음 | 대상 5명 → 쿼리 6개 | `.select_related("course")`, 대량이면 `iterator()` + `get_connection()` 하나로 묶어 발송 |
| D7 | 작음 | `settings.py:129` | `STAFF_NOTIFY_EMAILS`를 읽기만 하고 안 씀 → 담당자는 새 신청 알림을 못 받음 | grep 결과 사용처 없음 | 접수 시 담당자 알림 또는 아침 요약 메일, 아니면 설정 삭제 |
| D8 | 작음 | `send_contact_reminders.py:13` | 메일이 "연락 당일 아침"에만 감. 연락 날짜 전날 안내가 더 쓸모 있음(짐작, 기획 판단) | — | `--days-before` 옵션 |

## 5. 성능 (N+1)

| 번호 | 심각도 | 어디 | 무엇이 잘못됐나 | 재현 방법 | 고침 안 |
|---|---|---|---|---|---|
| E1 | 작음 | `applications/views.py:17`, `templates/manage/list.html:27` | 행마다 `course` 조회, 페이지네이션 없음 | 20행 → 쿼리 23개 | `select_related("course")`, `Paginator` |
| E2 | 작음 | `applications/api.py:15` | `course`, `course_title` 직렬화 N+1 | 20행 → 쿼리 22개 | `select_related("course")` |
| E3 | 작음 | `courses/api.py:10`, `courses/views.py:12` | 커리큘럼 N+1 | 교육 3개 → 쿼리 5개 | `prefetch_related("curriculum")` |

## 6. 구조 (Django 설계)

| 번호 | 심각도 | 어디 | 무엇이 잘못됐나 | 재현 방법 | 고침 안 |
|---|---|---|---|---|---|
| F1 | 큼 | `api.py:34-44`, `views.py:32-38`, `send_contact_reminders.py` | 비즈니스 규칙(신청 가능 여부, 상태 변경, 메일)이 뷰·명령에 흩어짐, 메일 발송 코드 중복 | 코드 읽음 | `applications/services.py`: `submit_application()`, `change_status(by=)`, `send_due_reminders(on=, dry_run=)`. 메일 문구는 `templates/emails/*.txt`. 뷰·API·admin·명령은 서비스만 호출 |
| F2 | 작음 | `courses/urls.py:4,11` | `courses` URL 파일이 `applications.views`를 가져옴 (앱 경계가 섞임) | 코드 읽음 | 신청 URL은 `applications/urls.py`로 |
| F3 | 작음 | `views.py:38`, `list.html:33` | 상태 바꾼 뒤 필터가 풀린 첫 화면으로 돌아감, 결과 메시지 없음, 선택만 바꿔도 즉시 제출 | 코드 읽음 | `next` 유지, `messages` 사용 |

## 7. 설정·배포

| 번호 | 심각도 | 어디 | 무엇이 잘못됐나 | 재현 방법 | 고침 안 |
|---|---|---|---|---|---|
| G1 | 큼 | `.github/workflows/ci.yml:37` | `check --deploy --fail-level ERROR`는 보안 경고(W)를 실패로 보지 않음 → 항상 통과. 문서는 "CI에서 점검한다"고 함 | 같은 명령 로컬 실행 → W004·W008 나오고 exit 0 | `--fail-level WARNING` + 의도한 것만 `SILENCED_SYSTEM_CHECKS` |
| G2 | 작음 | `settings.py:75-80` | `DATABASE_URL` 없으면 조용히 `postgres@127.0.0.1:5432`로 붙음. `CONN_HEALTH_CHECKS` 없음 | 코드 읽음 | 운영(DEBUG=0)에선 필수값으로, `conn_health_checks=True` |
| G3 | 작음 | `settings.py:97-106` | 운영만 `CompressedManifestStaticFilesStorage`. 테스트·CI는 DEBUG=1이라 템플릿의 없는 static 참조는 운영에서만 500 | 짐작 | 테스트도 Manifest 저장소로 돌리거나 CI에 DEBUG=0 스모크 요청 |
| G4 | 작음 | `requirements.txt` | `gspread`·`google-auth`는 쓰는 코드 없음. `tools/ui_check.py`가 쓰는 `playwright`는 없음. 운영·개발 의존성이 한 파일 | grep | `requirements/base.txt`·`dev.txt` 분리, 안 쓰는 것 제거 |
| G5 | 작음 | 저장소 루트 | README 없음(실행법·환경 변수·배치 등록법). `.env.example`에 SMTP 값 없음 | — | README에 5분 안에 띄우는 법, cron/EventBridge 예시 |
| G6 | 작음 | `Dockerfile:23` | gunicorn `--timeout`·graceful 설정 없음, 동기 SMTP와 겹치면 워커가 묶임(짐작) | — | D5 해결 + `--timeout 30` |

## 8. 테스트

| 번호 | 심각도 | 어디 | 무엇이 잘못됐나 | 재현 방법 | 고침 안 |
|---|---|---|---|---|---|
| H1 | 큼 | `tests/` | 배치 명령 테스트 0개 (중복·실패·대상 선정) | — | `call_command` + `mail.outbox`로 재실행 0통, 실패 건 계속 진행 |
| H2 | 큼 | `tests/` | `/manage/` 권한·상태 변경 테스트 0개 | — | 비로그인 302, 일반 사용자 차단, 잘못된 상태 400 |
| H3 | 작음 | `tests/` | 시간대 경계 테스트 없음 (KST 00:30 = UTC 전날) | — | `time-machine`으로 시간 고정 |
| H4 | 작음 | `tests/` | 메일 실패, 중복 신청, 마감일·정원, throttle 테스트 없음 | 이 리뷰의 scratch 테스트가 그대로 출발점 | 위 결함을 고치면서 회귀 테스트로 옮기기 |

---

## 채용 담당 Django 리드가 보고 싶어 할 텐데 없는 것

- **멱등한 배치 한 벌**: 발송 기록 표 + 유니크 제약 + `--dry-run`/`--date` + 실행 기록 + 실패 시 종료 코드. 문서에 이미 설계를 써 놨으니 그대로 구현하면 가장 큰 가산점이다.
- **서비스 계층과 트랜잭션 경계**: `services.py`, `transaction.on_commit` 발송, `select_for_update` 정원 처리.
- **DB 제약으로 지키는 규칙**: 중복 신청, 상태값.
- **구글 시트 내보내기** (가산 항목인데 의존성만 있음).
- **README**와 **AI 도구 사용 기록** (가산 항목, 저장소에 없음).
- 상태 변경 이력, 관리 화면 검색·페이지네이션, 담당자 알림.
