# 리팩토링 기록 — 1차 코드를 "운영 중인 기존 서비스"로 보고 고치기

공고의 주요 업무 중 **기존 서비스 개선 및 리팩토링**을 미리 보여 드리려고, 1차 커밋을 이미 운영 중인 서비스라고 가정하고 고쳤습니다.
원칙은 세 가지입니다.

1. **고치기 전에 재현한다.** 리뷰에서 나온 결함마다 먼저 실패하는 테스트를 만들었습니다(테스트 docstring에 "1차: …"로 남김).
2. **동작은 지키고 구조를 바꾼다.** 1차의 API 주소·응답 형태는 유지하고, 안쪽 구조와 규칙만 바꿨습니다.
3. **데이터도 운영 데이터처럼 다룬다.** 제약을 새로 걸 때 이미 쌓인 데이터가 깨지지 않게 했습니다.

커밋: `64ffdc0`(1차) → `96d5003`(서비스 계층) → `667fefe`(배치) → `1cc375d`(화면)

---

## 1. 비즈니스 규칙을 서비스 계층으로

**전 (1차)** — 규칙이 진입점마다 흩어져 있었습니다.

| 하는 일 | 있던 곳 |
|---|---|
| 신청 저장 + 접수 메일 | `ApplicationViewSet.perform_create` |
| 상태 변경 | 관리 화면 함수 뷰 (`request.POST["status"]`를 검증 없이 저장) |
| 연락일 안내 메일 | 관리 명령 `send_contact_reminders` (메일 코드가 위와 따로 한 벌 더) |
| 날짜 규칙 | 시리얼라이저(서버)와 `apply.js`(브라우저, UTC 계산)에 따로 |

**후 (2차)**

```
applications/
  rules.py       규칙만: 연락 날짜 범위(KST 내일~30일, 평일), 신청 가능 여부(열림·마감일·정원)
  services.py    쓰기: submit_application(), change_status(), update_memo()
  selectors.py   읽기: application_list(필터·검색·정렬), status_counts(), todo_counts()
  serializers.py 형식 검사만 하고 서비스 호출
  api.py / views.py / admin.py   서비스·셀렉터만 부름
automation/
  mailer.py      모든 신청자 메일의 단일 출구 (발송 기록·중복 방지·재시도)
  jobs.py        배치 작업들 (날짜를 인자로 받아 재처리·테스트 가능)
```

- admin에서 상태를 바꿔도 `save_model`이 `change_status()`를 거쳐 **변경 이력**이 남습니다. 진입점이 네 개(API·관리 화면·admin·배치)여도 규칙은 한 곳입니다.
- 화면의 날짜 칩, API 검증, 배치 대상 선정이 모두 `rules.py` 하나를 봅니다. 1차에서는 브라우저가 `toISOString()`(UTC)으로 최소 날짜를 잡아, 한국 시간 0~9시에는 하루가 어긋났습니다(`tests/test_manage.py::test_rules_use_korean_today_not_utc`).

## 2. 트랜잭션 경계

| 문제 (1차) | 고친 방법 (2차) | 테스트 |
|---|---|---|
| SMTP가 실패하면 신청은 저장된 채 500 → 사용자가 다시 눌러 중복 | 메일은 `transaction.on_commit` 뒤에 발송. 실패하면 `NotificationLog`에 FAILED로 남고 다음 배치가 재시도. 신청은 201 | `test_mail_failure_does_not_fail_the_application` |
| 정원 1명인 교육에 3명 모두 접수 | 교육 행을 `select_for_update()`로 잠그고 센다. 마지막 한 자리에 동시에 들어와도 한 명만 | `test_closed_course_deadline_and_capacity` |
| 같은 사람 같은 교육 중복 접수, 이메일 대소문자 그대로 | 서비스 검사 + DB 유니크 제약 `Lower(email), course` (검사와 저장 사이 경쟁은 `IntegrityError`로 잡음) | `test_duplicate_application_rejected_case_insensitive` |
| 상태값 아무 문자열이나 저장 | 서비스 검증 + DB `CheckConstraint` | `test_form_status_change_validates` |

## 3. 운영 데이터가 있는 상태에서 제약 추가하기

유니크 제약을 거는 마이그레이션을 로컬 DB에 적용하자 실제로 실패했습니다.
1차의 "중복 신청을 막지 않는다" 결함 때문에 점검 도구가 넣은 같은 이메일 신청 13건이 쌓여 있었기 때문입니다.

```
django.db.utils.IntegrityError: could not create unique index "uniq_application_email_per_course"
DETAIL:  Key (lower(email::text), course_id)=(ui-check@example.com, 1) is duplicated.
```

그래서 제약을 걸기 전에 **데이터 마이그레이션**으로 정리했습니다(`applications/migrations/0002_…py`의 `merge_duplicate_applications`).

- 같은 교육·같은 이메일(대소문자 무시) 묶음마다 **가장 먼저 들어온 신청을 남깁니다**
- 나중 신청의 이름·주소·연락일은 남긴 신청의 **담당자 메모에 기록한 뒤** 지웁니다. 정보를 잃지 않습니다
- 상태는 묶음 중 가장 진행된 것을 따릅니다(접수 < 확인중 < 완료)
- 결과: 13건 → 1건, 메모에 12줄 기록. 그 뒤 제약이 정상 적용

운영이라면 이 마이그레이션 전에 같은 조회로 몇 건이 합쳐지는지 먼저 보고하고, 스냅샷을 뜬 뒤 적용합니다.

## 4. 배치를 멱등하게

| | 1차 `send_contact_reminders` | 2차 `run_daily_jobs` |
|---|---|---|
| 두 번 실행 | 3명에게 6통 | 3통 (두 번째 실행은 `skipped: 3`) |
| 중간에 한 건 실패 | 예외로 전체 중단, 다시 돌리면 앞사람이 또 받음 | 그 건만 FAILED, 나머지 발송, 다음 배치가 재시도 |
| 시험 실행 | 없음 | `--dry-run` (보낼 건수만 계산, 기록 안 남김) |
| 지난 날짜 재처리 | 없음 | `--date 2026-12-01` |
| 실행 기록 | 없음 | 작업마다 `JobRun`(시작·끝·처리 건수·오류), 관리 화면 "배치 이력" |
| 실패 알림 | 없음 | 하나라도 실패하면 종료 코드 1 → 스케줄러가 알림 |
| 동시 실행 | 고려 안 함 | 발송 권리를 조건부 UPDATE로 먼저 잡은 쪽만 보냄 |

테스트: `tests/test_batch.py` (재실행 0통, 한 건 실패 후 재시도, dry-run, 완료 건 제외, 하루 한 번 요약, 실패 기록·종료 코드, 시트 내보내기)

## 5. 쿼리 수

| 화면 / API | 1차 | 2차 |
|---|---|---|
| 관리 목록 | 20행 → 쿼리 23개 (행마다 교육 조회) | 3행이든 25행이든 **10개** (`test_manage_list_query_count_does_not_grow_with_rows`) |
| `GET /api/applications/` | 20행 → 22개 | 3개 이하 (`select_related`) |
| `GET /api/courses/` | 교육 수만큼 커리큘럼 조회 | 3개 이하 (`prefetch_related`) |

1차 수치는 코드 리뷰어가 1차 커밋에서 직접 잰 값입니다(`docs/review/CODE_REVIEW.md` E1~E3).

## 6. 하지 않은 것 (이유)

- **Celery 같은 작업 큐**: 메일 양이 적고(하루 수십~수백 통), 실패는 배치가 재시도하므로 지금은 큐를 운영할 만큼 이득이 없습니다. 트래픽이 커지면 `mailer.deliver()`를 큐 작업으로 감싸면 되도록 출구를 하나로 모아 뒀습니다.
- **공휴일 제외**: `rules.is_contact_day()` 한 곳에서 처리하게 해 뒀지만, 공휴일 데이터 출처(공공데이터 API 등)는 운영 정책이 정해지면 붙입니다.
- **신청 취소 상태**: 과제의 상태(접수/확인중/완료)를 그대로 지켰습니다. 취소가 생기면 유니크 제약에 `condition=~Q(status="canceled")`를 더하면 됩니다.
