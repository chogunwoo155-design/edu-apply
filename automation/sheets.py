"""
신청 목록 → Google Spreadsheet 내보내기.

설정(환경 변수):
    GOOGLE_SHEET_ID                 내보낼 스프레드시트 ID (URL의 /d/<ID>/)
    GOOGLE_SERVICE_ACCOUNT_FILE     서비스 계정 키 JSON 파일 경로   (둘 중 하나)
    GOOGLE_SERVICE_ACCOUNT_JSON     서비스 계정 키 JSON 문자열      (Secrets Manager 주입용)

스프레드시트는 서비스 계정 이메일에 '편집자'로 공유해 두어야 한다.
내보내기는 '전체 스냅샷 덮어쓰기'다. 여러 번 돌려도 결과가 같고(멱등),
시트에서 누가 행을 지워도 다음 실행에서 원래대로 돌아온다.
"""

from __future__ import annotations

import json
import os
from typing import Protocol, Sequence

from django.utils import timezone

HEADER = ["신청번호", "신청일시", "교육", "이름", "이메일", "우편번호", "주소", "연락 가능 날짜", "연락 시간대", "상태", "담당자 메모"]
WORKSHEET_TITLE = "신청목록"


class SheetWriter(Protocol):
    def replace_all(self, rows: Sequence[Sequence[str]]) -> None: ...


def application_rows(applications) -> list[list[str]]:
    rows = []
    for a in applications:
        rows.append(
            [
                a.reference,
                timezone.localtime(a.created_at).strftime("%Y-%m-%d %H:%M"),
                a.course.title,
                a.name,
                a.email,
                a.postcode,
                a.full_address,
                a.contact_date.isoformat(),
                a.get_contact_time_display(),
                a.get_status_display(),
                a.admin_memo,
            ]
        )
    return rows


def is_configured() -> bool:
    return bool(os.environ.get("GOOGLE_SHEET_ID")) and bool(
        os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE") or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    )


class GoogleSheetWriter:
    def __init__(self) -> None:
        import gspread  # 설정된 환경에서만 불러온다

        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        client = (
            gspread.service_account_from_dict(json.loads(raw))
            if raw
            else gspread.service_account(filename=os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"])
        )
        book = client.open_by_key(os.environ["GOOGLE_SHEET_ID"])
        try:
            self.ws = book.worksheet(WORKSHEET_TITLE)
        except gspread.WorksheetNotFound:
            self.ws = book.add_worksheet(WORKSHEET_TITLE, rows=1000, cols=len(HEADER))

    def replace_all(self, rows: Sequence[Sequence[str]]) -> None:
        self.ws.clear()
        self.ws.update([HEADER, *rows], value_input_option="RAW")
        self.ws.freeze(rows=1)


def get_writer() -> SheetWriter | None:
    return GoogleSheetWriter() if is_configured() else None
