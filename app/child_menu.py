"""M15: CHILD_BEGINNER(10세 이하) 전용 메인 메뉴.

사용자 요청에 따라 GENERAL/CHILD_BRIDGE의 메뉴(app/menu.py)를 그대로 쓰지 않고,
학습 내용이 완전히 다른 어린이 커리큘럼(Stage0~5)에 맞춰 아주 단순한 전용 메뉴를 별도로 둔다.
"""

from app.telegram_client import build_reply_keyboard

STUDY = "🎈 오늘 공부하기"
PROGRESS = "⭐ 내 진도"


def build_child_menu_keyboard() -> dict:
    return build_reply_keyboard([[STUDY], [PROGRESS]])
