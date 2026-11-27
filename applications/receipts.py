"""
접수증 링크. 신청 직후 화면이 이 주소로 바뀐다(location.replace).
- 새로고침·뒤로 가기를 해도 빈 신청서가 다시 뜨지 않는다 (1차: 같은 신청을 또 넣기 쉬웠다)
- 신청 ID를 서명해서 넣으므로 다른 사람의 접수증을 번호로 넘겨 볼 수 없다. 7일 뒤 만료.
"""

from django.core import signing
from django.urls import reverse

SALT = "applications.receipt"
MAX_AGE = 60 * 60 * 24 * 7


def make_url(application) -> str:
    token = signing.dumps(application.pk, salt=SALT, compress=True)
    return reverse("applications:receipt", args=[token])


def read_token(token: str) -> int | None:
    try:
        return signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return None
