import logging
from datetime import date, timedelta

from app import menu, planner, srs, today_session
from app.config import settings
from app.conversation import chat as conversation_chat
from app.conversation import service as conversation_service
from app.custom_text import extractor as custom_text_extractor
from app.custom_text import feedback as custom_text_feedback
from app.custom_text import service as custom_text_service
from app.db import db_available
from app.grammar import service as grammar_service
from app.modes import determine_learning_mode
from app.placement import service as placement_service
from app.placement.questions import Question
from app.reading import evaluator as reading_evaluator
from app.reading import service as reading_service
from app.repo import content as content_repo
from app.repo import conversation as conversation_repo
from app.repo import custom_text as custom_text_repo
from app.repo import grammar as grammar_repo
from app.repo import learning_sessions as learning_sessions_repo
from app.repo import placement as placement_repo
from app.repo import reading as reading_repo
from app.repo import school_assignment as school_assignment_repo
from app.repo import school_exams as school_exams_repo
from app.repo import user_words as user_words_repo
from app.repo import users as users_repo
from app.school_assignment import analyzer as school_assignment_analyzer
from app.school_assignment import service as school_assignment_service
from app.school_exam import registration as exam_registration_service
from app.school_exam import review_service as exam_review_service
from app.telegram_client import (
    answer_callback_query,
    build_inline_keyboard,
    delete_message,
    send_message,
)
from app.vocab import service as vocab_service
from app.vocab.quiz import build_choices, is_meaning_match

logger = logging.getLogger(__name__)

# 레벨진단이 있는 모드. CHILD_BEGINNER는 별도 커리큘럼(Stage0~)으로 진입한다 (섹션8-1, 8-5).
PLACEMENT_MODES = {"GENERAL", "CHILD_BRIDGE"}


async def handle_update(update: dict) -> None:
    """모든 텔레그램 업데이트의 진입점. user_id 확인 -> 승인여부 확인 -> 라우팅 (섹션 15-1)."""
    if not db_available():
        logger.warning("DB unavailable — dropping update")
        return

    if "callback_query" in update:
        await _handle_callback_query(update["callback_query"])
        return

    message = update.get("message")
    if not message:
        return

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    # 인증은 텔레그램이 전달한 chat.id를 기준으로 하며, 별도 파라미터의 user_id는 신뢰하지 않는다 (섹션19-9).
    telegram_id = str(chat_id)
    text = (message.get("text") or "").strip()

    if telegram_id == settings.admin_telegram_id:
        await _ensure_admin_registered(telegram_id)

    user = await users_repo.get_user_by_telegram_id(telegram_id)

    if text == "/start":
        await _handle_start(telegram_id, chat_id, user)
        return

    if user is None:
        await send_message(chat_id, "먼저 /start 를 입력해 주세요.")
        return

    if not user["approved"]:
        await send_message(chat_id, "아직 승인 대기 중입니다. 관리자 승인을 기다려 주세요.")
        return

    await users_repo.touch_last_active(telegram_id)

    if telegram_id == settings.admin_telegram_id and (text.startswith("/승인 ") or text.startswith("/approve ")):
        await _handle_admin_approve(chat_id, text)
        return

    if telegram_id == settings.admin_telegram_id and text in ("/대기목록", "/pending"):
        await _handle_admin_list_pending(chat_id)
        return

    if telegram_id == settings.admin_telegram_id and text in ("/사용자목록", "/users"):
        await _handle_admin_list_users(chat_id)
        return

    if user["learning_mode"] is None:
        await _handle_age_input(telegram_id, chat_id, text)
        return

    if vocab_service.current_stage(telegram_id) == "subjective":
        await _handle_vocab_subjective_answer(telegram_id, chat_id, user, text)
        return

    if reading_service.is_active(telegram_id):
        await _handle_reading_answer(telegram_id, chat_id, user, text)
        return

    if conversation_service.is_active(telegram_id):
        await _handle_conversation_message(telegram_id, chat_id, user, text)
        return

    custom_text_session = custom_text_service.get_session(telegram_id)
    if custom_text_session is not None and custom_text_session.stage in ("awaiting_text", "awaiting_translation"):
        await _handle_custom_text_message(telegram_id, chat_id, user, text)
        return

    school_assignment_session = school_assignment_service.get_session(telegram_id)
    if school_assignment_session is not None and school_assignment_session.stage == "awaiting_text":
        await _handle_school_assignment_pasted(telegram_id, chat_id, user, school_assignment_session, text)
        return

    exam_registration_session = exam_registration_service.get_session(telegram_id)
    if exam_registration_session is not None:
        await _handle_exam_registration_message(telegram_id, chat_id, user, exam_registration_session, text)
        return

    is_admin = telegram_id == settings.admin_telegram_id

    # 명령어는 띄어쓰기에 관대하게 처리 (예: "/단어 학습"도 "/단어학습"으로 인식). 메뉴 버튼 라벨은 그대로 비교.
    normalized_command = text.replace(" ", "") if text.startswith("/") else text

    if normalized_command in ("/메뉴", "메뉴", "/menu"):
        await _send_main_menu(chat_id, is_admin)
        return

    if normalized_command in ("/레벨진단", "/leveltest") and user["learning_mode"] in PLACEMENT_MODES:
        await _start_placement(telegram_id, chat_id)
        return

    if (
        normalized_command in ("/오늘학습", menu.TODAY_LEARNING, "/todaylearning")
        and user["learning_mode"] in PLACEMENT_MODES
    ):
        await _start_today_session(telegram_id, chat_id, user)
        return

    if normalized_command in ("/단어학습", menu.VOCAB_STUDY, "/vocabstudy") and user["learning_mode"] in PLACEMENT_MODES:
        await _start_vocab_session(telegram_id, chat_id, user)
        return

    if normalized_command in ("/단어시험", menu.VOCAB_QUIZ, "/vocabquiz") and user["learning_mode"] in PLACEMENT_MODES:
        await _start_vocab_quiz(telegram_id, chat_id, user)
        return

    if normalized_command in ("/문법학습", menu.GRAMMAR_STUDY, "/grammarstudy") and user["learning_mode"] in PLACEMENT_MODES:
        await _start_grammar_session(telegram_id, chat_id, user, is_review=False)
        return

    if normalized_command in ("/복습", menu.REVIEW, "/review") and user["learning_mode"] in PLACEMENT_MODES:
        await _start_grammar_session(telegram_id, chat_id, user, is_review=True)
        return

    if normalized_command in ("/해석", menu.READING, "/reading") and user["learning_mode"] in PLACEMENT_MODES:
        await _start_reading_session(telegram_id, chat_id, user, is_review=False)
        return

    if (
        normalized_command in ("/회화", menu.CONVERSATION, "/conversation")
        and user["learning_mode"] in PLACEMENT_MODES
    ):
        await _start_conversation_session(telegram_id, chat_id, user)
        return

    if (
        normalized_command in ("/진도", menu.PROGRESS, "/progress")
        and user["learning_mode"] in PLACEMENT_MODES
    ):
        await _handle_progress(telegram_id, chat_id, user)
        return

    if (
        normalized_command in ("/텍스트학습", menu.TEXT_PASTE, "/customtext")
        and user["learning_mode"] in PLACEMENT_MODES
    ):
        await _start_custom_text_session(telegram_id, chat_id, user)
        return

    if (
        normalized_command in ("/수행평가", menu.SCHOOL_ASSIGNMENT, "/schooltask")
        and user["learning_mode"] in PLACEMENT_MODES
    ):
        await _start_school_assignment_session(telegram_id, chat_id, user)
        return

    if normalized_command in ("/시험관리", menu.SCHOOL_EXAM) and user["learning_mode"] in PLACEMENT_MODES:
        await _send_school_exam_menu(chat_id, is_admin)
        return

    if normalized_command in ("/시험등록", "/examregister") and user["learning_mode"] in PLACEMENT_MODES:
        await _start_exam_registration(telegram_id, chat_id)
        return

    if normalized_command in ("/시험목록", "/examlist") and user["learning_mode"] in PLACEMENT_MODES:
        await _handle_exam_list(telegram_id, chat_id, user)
        return

    if normalized_command in ("/시험직전복습", "/examreview") and user["learning_mode"] in PLACEMENT_MODES:
        await _start_exam_review(telegram_id, chat_id, user)
        return

    if text == menu.ADMIN and is_admin:
        await _send_admin_menu(chat_id)
        return

    if text in menu.NOT_YET_IMPLEMENTED:
        await send_message(
            chat_id,
            f"'{menu.NOT_YET_IMPLEMENTED[text]}' 기능은 다음 마일스톤에서 연결됩니다.",
            reply_markup=menu.build_main_menu_keyboard(is_admin),
        )
        return

    # 인식하지 못한 입력 — 메뉴를 다시 보여준다 (M12 이후 학교시험/어린이모드 등에서 새 분기가 추가될 자리)
    await send_message(
        chat_id,
        f"무슨 말씀인지 이해하지 못했어요. 아래 메뉴에서 골라주세요.\n"
        f"학습 모드: {user['learning_mode']}"
        + (f" / 레벨: {user['placement_level']}" if user["placement_level"] else ""),
        reply_markup=menu.build_main_menu_keyboard(is_admin),
    )


async def _handle_callback_query(callback_query: dict) -> None:
    callback_id = callback_query.get("id")
    data = callback_query.get("data") or ""
    from_user = callback_query.get("from") or {}
    telegram_id = str(from_user.get("id"))
    tg_message = callback_query.get("message") or {}
    chat_id = (tg_message.get("chat") or {}).get("id")
    message_id = tg_message.get("message_id")

    await answer_callback_query(callback_id)

    if chat_id is None:
        return

    # 버튼을 누른 카드/문제 메시지는 항상 지운다 — 답한 화면이 채팅에 계속 남아 헷갈리는 것을 방지.
    # DB에 저장된 학습 기록(정답 여부, SRS 상태 등)은 이 삭제와 무관하게 그대로 유지된다.
    if message_id is not None:
        await delete_message(chat_id, message_id)

    parts = data.split(":")

    if len(parts) == 3 and parts[0] == "placement":
        await _handle_placement_answer(telegram_id, chat_id, parts[1], int(parts[2]))
        return

    if parts[0] == "vocab" and len(parts) == 3 and parts[1] in ("known", "unknown"):
        word_id = int(parts[2])
        if parts[1] == "known":
            await _handle_vocab_known(telegram_id, chat_id, word_id)
        else:
            await _handle_vocab_unknown(telegram_id, chat_id, word_id)
        return

    if parts[0] == "vocab" and len(parts) == 4 and parts[1] == "mcq":
        await _handle_vocab_mcq_answer(telegram_id, chat_id, int(parts[2]), int(parts[3]))
        return

    if parts[0] == "vocabquiz" and len(parts) == 3:
        await _handle_vocab_quiz_answer(telegram_id, chat_id, int(parts[1]), int(parts[2]))
        return

    if parts[0] == "grammar" and len(parts) == 3:
        await _handle_grammar_answer(telegram_id, chat_id, int(parts[1]), int(parts[2]))
        return

    if parts[0] == "examquiz" and len(parts) == 3:
        await _handle_school_assignment_exam_answer(telegram_id, chat_id, int(parts[1]), int(parts[2]))
        return

    if parts[0] == "schoolexamlink" and len(parts) == 2:
        exam_id = None if parts[1] == "none" else int(parts[1])
        await _handle_school_assignment_exam_link(telegram_id, chat_id, exam_id)
        return

    if parts[0] == "examreviewpick" and len(parts) == 2:
        await _handle_exam_review_pick(telegram_id, chat_id, int(parts[1]))
        return

    if parts[0] == "examreviewquiz" and len(parts) == 3:
        await _handle_exam_review_answer(telegram_id, chat_id, int(parts[1]), int(parts[2]))
        return


async def _ensure_admin_registered(telegram_id: str) -> None:
    existing = await users_repo.get_user_by_telegram_id(telegram_id)
    if existing is not None:
        if existing["role"] != "admin" or not existing["approved"]:
            await users_repo.approve_user(telegram_id)
            await users_repo.set_role(telegram_id, "admin")
        return

    await users_repo.create_pending_user(telegram_id)
    await users_repo.approve_user(telegram_id)
    await users_repo.set_role(telegram_id, "admin")


async def _handle_start(telegram_id: str, chat_id: int, user) -> None:
    if user is None:
        await users_repo.create_pending_user(telegram_id)
        await send_message(chat_id, "승인 대기 등록되었습니다. 관리자 승인 후 이용하실 수 있습니다.")
        if settings.admin_telegram_id:
            await send_message(
                settings.admin_telegram_id,
                f"새 사용자 승인 대기: {telegram_id}\n승인하려면 다음을 보내세요:\n/승인 {telegram_id}",
            )
        return

    if not user["approved"]:
        await send_message(chat_id, "아직 승인 대기 중입니다. 관리자 승인을 기다려 주세요.")
        return

    if user["learning_mode"] is None:
        await send_message(chat_id, "나이를 숫자로 입력해 주세요. (예: 13)")
        return

    if user["learning_mode"] in PLACEMENT_MODES and not user["placement_level"]:
        await _start_placement(telegram_id, chat_id)
        return

    await send_message(
        chat_id,
        f"환영합니다. 현재 학습 모드: {user['learning_mode']}",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


async def _send_main_menu(chat_id: int, is_admin: bool) -> None:
    await send_message(chat_id, "메뉴에서 선택해 주세요.", reply_markup=menu.build_main_menu_keyboard(is_admin))


async def _send_admin_menu(chat_id: int) -> None:
    await send_message(
        chat_id,
        "관리자 명령어\n"
        "/대기목록 - 승인 대기 사용자 목록\n"
        "/승인 <telegram_id> - 사용자 승인\n"
        "/사용자목록 - 전체 사용자 현황 (아이디/나이/모드/오늘활동)",
    )


async def _handle_age_input(telegram_id: str, chat_id: int, text: str) -> None:
    if not text.isdigit():
        await send_message(chat_id, "나이를 숫자로 입력해 주세요. (예: 13)")
        return

    age = int(text)
    mode = determine_learning_mode(age)
    await users_repo.set_age_and_mode(telegram_id, age, mode)
    await send_message(chat_id, f"학습 모드가 {mode}로 설정되었습니다.")

    if mode in PLACEMENT_MODES:
        await _start_placement(telegram_id, chat_id)
    else:
        # CHILD_BEGINNER: Stage0(Alphabet)부터 시작 — M15에서 구현 예정
        await send_message(chat_id, "어린이 학습 과정(알파벳부터)은 다음 마일스톤에서 연결됩니다.")


def _question_keyboard(question: Question) -> dict:
    buttons = [(choice, f"placement:{question.id}:{idx}") for idx, choice in enumerate(question.choices)]
    return build_inline_keyboard(buttons, columns=1)


async def _send_question(chat_id: int, question: Question) -> None:
    label = "[단어]" if question.kind == "word" else "[문법]"
    await send_message(chat_id, f"{label} {question.prompt}", reply_markup=_question_keyboard(question))


async def _start_placement(telegram_id: str, chat_id: int) -> None:
    question = placement_service.start_session(telegram_id)
    await send_message(chat_id, "레벨 진단을 시작합니다. 총 10문항, 버튼으로 답해주세요.")
    await _send_question(chat_id, question)


async def _handle_placement_answer(telegram_id: str, chat_id: int, question_id: str, choice_index: int) -> None:
    result = placement_service.submit_answer(telegram_id, question_id, choice_index)
    if result is None:
        await send_message(
            chat_id,
            "이미 처리된 문항이거나 세션이 만료되었습니다. /레벨진단으로 다시 시작해 주세요.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    if not result.finished:
        await _send_question(chat_id, result.next_question)
        return

    user = await users_repo.get_user_by_telegram_id(telegram_id)
    if user is not None:
        await users_repo.set_placement_level(telegram_id, result.level)
        await placement_repo.save_result(
            user["id"],
            result.word_correct,
            result.word_total,
            result.grammar_correct,
            result.grammar_total,
            result.level,
        )

    await send_message(
        chat_id,
        "레벨 진단 완료!\n"
        f"단어 {result.word_correct}/{result.word_total}, 문법 {result.grammar_correct}/{result.grammar_total}\n"
        f"산출된 레벨: {result.level}",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


async def _build_vocab_queue(user) -> list[vocab_service.WordItem]:
    today = date.today()
    due_rows = await user_words_repo.get_due_review_words(user["id"], today)
    new_limit = user["daily_new_word_limit"] or srs.DEFAULT_DAILY_NEW_WORDS
    level = user["placement_level"] or "beginner"
    new_rows = await user_words_repo.get_new_words(user["id"], level, new_limit)

    items = [
        vocab_service.WordItem(
            word_id=row["word_id"],
            word=row["word"],
            meaning_ko=row["meaning_ko"],
            pronunciation=row["pronunciation"],
            example_sentence=row["example_sentence"],
            example_translation=row["example_translation"],
            level=row["level"],
            ease=float(row["ease"]),
            interval_days=row["interval_days"],
            is_new=False,
        )
        for row in due_rows
    ]
    items += [
        vocab_service.WordItem(
            word_id=row["word_id"],
            word=row["word"],
            meaning_ko=row["meaning_ko"],
            pronunciation=row["pronunciation"],
            example_sentence=row["example_sentence"],
            example_translation=row["example_translation"],
            level=row["level"],
            ease=srs.INITIAL_EASE,
            interval_days=srs.INITIAL_INTERVAL_DAYS,
            is_new=True,
        )
        for row in new_rows
    ]
    return items


def _word_card_text(item: vocab_service.WordItem) -> str:
    lines = [f"📘 {item.word}", f"뜻: {item.meaning_ko}"]
    if item.pronunciation:
        lines.append(f"발음: {item.pronunciation}")
    if item.example_sentence:
        lines.append(f"예문: {item.example_sentence}")
    if item.example_translation:
        lines.append(f"해석: {item.example_translation}")
    return "\n".join(lines)


async def _send_word_card(chat_id: int, item: vocab_service.WordItem) -> None:
    keyboard = build_inline_keyboard(
        [("아는단어", f"vocab:known:{item.word_id}"), ("모르는단어", f"vocab:unknown:{item.word_id}")],
        columns=2,
    )
    await send_message(chat_id, _word_card_text(item), reply_markup=keyboard)


async def _start_vocab_session(telegram_id: str, chat_id: int, user) -> bool:
    items = await _build_vocab_queue(user)
    if not items:
        await send_message(
            chat_id,
            "오늘 학습할 단어가 없습니다. (콘텐츠뱅크가 부족하거나 이미 모두 학습했어요)",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return False

    first = vocab_service.start_session(telegram_id, items)
    await send_message(chat_id, f"단어 학습을 시작합니다. 총 {len(items)}개, [아는단어]/[모르는단어]로 답해주세요.")
    await _send_word_card(chat_id, first)
    return True


async def _finish_vocab_word(telegram_id: str, chat_id: int, user) -> None:
    next_item = vocab_service.advance(telegram_id)
    if next_item is not None:
        await _send_word_card(chat_id, next_item)
        return

    summary = vocab_service.finish_session(telegram_id)

    custom_text_session = custom_text_service.get_session(telegram_id)
    if custom_text_session is not None and custom_text_session.stage == "cards":
        # 텍스트 붙여넣기 학습(M11)에서 추출한 단어 카드 — 신규단어 수 자동조절 대상이 아니라 여기서 마무리.
        custom_text_service.enter_translation_stage(telegram_id)
        await send_message(
            chat_id,
            f"단어 카드 학습 완료! 이제 전체 텍스트를 한국어로 해석해서 보내주세요.\n\n{custom_text_session.text}",
        )
        return

    school_assignment_session = school_assignment_service.get_session(telegram_id)
    if school_assignment_session is not None and school_assignment_session.stage == "cards":
        # 학교 수행평가 학습(M12)에서 추출한 단어 카드 — 신규단어 수 자동조절 대상이 아니라 여기서 마무리.
        await send_message(chat_id, "단어 카드 학습 완료! 이제 지문의 핵심 문법과 예상 시험문제를 준비할게요...")
        await _start_school_assignment_exam(
            telegram_id, chat_id, user, school_assignment_session.level, school_assignment_session.text
        )
        return

    accuracy = summary.correct / summary.reviewed if summary.reviewed else 1.0
    current_limit = user["daily_new_word_limit"] or srs.DEFAULT_DAILY_NEW_WORDS
    new_limit = srs.adjust_daily_new_word_limit(current_limit, accuracy)
    if new_limit != current_limit:
        await users_repo.set_daily_new_word_limit(telegram_id, new_limit)

    if today_session.is_active(telegram_id):
        await learning_sessions_repo.mark_stage_complete(user["id"], "vocab")
        await send_message(chat_id, f"단어 학습 완료! {summary.reviewed}개 중 {summary.correct}개 성공")
        await _advance_today_session(telegram_id, chat_id, user)
        return

    await send_message(
        chat_id,
        f"오늘의 단어 학습 완료! {summary.reviewed}개 중 {summary.correct}개 성공\n"
        f"다음 신규 단어는 하루 {new_limit}개로 진행됩니다.",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


async def _handle_vocab_known(telegram_id: str, chat_id: int, word_id: int) -> None:
    item = vocab_service.current_item(telegram_id)
    if item is None or item.word_id != word_id:
        return

    user = await users_repo.get_user_by_telegram_id(telegram_id)
    result = srs.apply_correct(item.interval_days, item.ease)
    await user_words_repo.upsert_word_progress(
        user["id"],
        word_id,
        "known",
        result.ease,
        result.interval_days,
        date.today() + timedelta(days=result.interval_days),
    )
    vocab_service.record_result(telegram_id, True)
    await _finish_vocab_word(telegram_id, chat_id, user)


async def _handle_vocab_unknown(telegram_id: str, chat_id: int, word_id: int) -> None:
    item = vocab_service.current_item(telegram_id)
    if item is None or item.word_id != word_id:
        return
    if vocab_service.current_stage(telegram_id) != "card":
        return  # 이미 처리된 카드에 대한 중복/지연된 클릭 무시

    distractors = await user_words_repo.get_distractor_meanings(item.level, word_id, 3)
    choices, correct_index = build_choices(item.meaning_ko, distractors)
    vocab_service.enter_mcq_stage(telegram_id, choices, correct_index)

    keyboard = build_inline_keyboard(
        [(choice, f"vocab:mcq:{word_id}:{idx}") for idx, choice in enumerate(choices)],
        columns=1,
    )
    await send_message(chat_id, f"'{item.word}'의 뜻은 무엇일까요?", reply_markup=keyboard)


async def _handle_vocab_mcq_answer(telegram_id: str, chat_id: int, word_id: int, choice_index: int) -> None:
    item = vocab_service.current_item(telegram_id)
    if item is None or item.word_id != word_id or vocab_service.current_stage(telegram_id) != "mcq":
        return

    choices, correct_index = vocab_service.get_mcq(telegram_id)
    is_correct = choice_index == correct_index
    feedback = "정답입니다!" if is_correct else f"오답입니다. 정답은 '{choices[correct_index]}' 입니다."
    vocab_service.enter_subjective_stage(telegram_id)
    await send_message(chat_id, f"{feedback}\n이번엔 직접 입력해보세요 — '{item.word}'의 뜻은?")


async def _handle_vocab_subjective_answer(telegram_id: str, chat_id: int, user, text: str) -> None:
    item = vocab_service.current_item(telegram_id)
    if item is None:
        return

    is_correct = is_meaning_match(text, item.meaning_ko)
    result = (
        srs.apply_correct(item.interval_days, item.ease)
        if is_correct
        else srs.apply_incorrect(item.interval_days, item.ease)
    )
    await user_words_repo.upsert_word_progress(
        user["id"],
        item.word_id,
        "learning",
        result.ease,
        result.interval_days,
        date.today() + timedelta(days=result.interval_days),
    )
    vocab_service.record_result(telegram_id, is_correct)

    feedback = "정답입니다!" if is_correct else f"아쉬워요. 정답은 '{item.meaning_ko}' 입니다."
    await send_message(chat_id, feedback)
    await _finish_vocab_word(telegram_id, chat_id, user)


async def _start_vocab_quiz(telegram_id: str, chat_id: int, user) -> None:
    rows = await user_words_repo.get_learned_words_sample(user["id"], 5)
    if not rows:
        await send_message(
            chat_id,
            "아직 학습한 단어가 없습니다. 먼저 /단어학습을 진행해 주세요.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    items = []
    for row in rows:
        distractors = await user_words_repo.get_distractor_meanings(row["level"], row["word_id"], 3)
        choices, correct_index = build_choices(row["meaning_ko"], distractors)
        items.append(
            vocab_service.QuizItem(word_id=row["word_id"], word=row["word"], choices=choices, correct_index=correct_index)
        )

    first = vocab_service.start_quiz(telegram_id, items)
    await send_message(chat_id, f"단어 시험을 시작합니다. 총 {len(items)}문항.")
    await _send_quiz_question(chat_id, first)


async def _send_quiz_question(chat_id: int, item: vocab_service.QuizItem) -> None:
    keyboard = build_inline_keyboard(
        [(choice, f"vocabquiz:{item.word_id}:{idx}") for idx, choice in enumerate(item.choices)],
        columns=1,
    )
    await send_message(chat_id, f"'{item.word}'의 뜻은?", reply_markup=keyboard)


async def _handle_vocab_quiz_answer(telegram_id: str, chat_id: int, word_id: int, choice_index: int) -> None:
    result = vocab_service.submit_quiz_answer(telegram_id, word_id, choice_index)
    if result is None:
        await send_message(
            chat_id,
            "이미 처리된 문항이거나 세션이 만료되었습니다. /단어시험으로 다시 시작해 주세요.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    if not result.finished:
        await _send_quiz_question(chat_id, result.next_item)
        return

    await send_message(
        chat_id,
        f"단어 시험 완료! {result.total}문제 중 {result.correct}개 정답",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


GRAMMAR_SESSION_SIZE = 5


async def _start_grammar_session(telegram_id: str, chat_id: int, user, is_review: bool) -> bool:
    if not is_review and user["role"] != "admin":  # 관리자는 하루 1회 제한 없이 계속 테스트 가능 (사용자 요청)
        already_done = await grammar_repo.has_completed_new_session_today(user["id"])
        if already_done:
            await send_message(
                chat_id,
                "오늘의 신규 문법 학습은 이미 완료했습니다. 아래 🔁 복습 버튼으로 반복할 수 있어요.",
                reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
            )
            return False

    level = user["placement_level"] or "beginner"
    rows = await grammar_repo.get_random_questions(level, GRAMMAR_SESSION_SIZE)
    if not rows:
        await send_message(
            chat_id,
            "아직 학습할 문법 문제가 없습니다.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return False

    items = [
        grammar_service.GrammarQuestion(
            question_id=row["id"],
            topic=row["topic"],
            concept_intro=row["concept_intro"],
            prompt=row["prompt"],
            choices=row["choices"],
            correct_index=row["correct_index"],
            explanation=row["explanation"],
        )
        for row in rows
    ]
    first = grammar_service.start_session(telegram_id, items, is_review)
    label = "복습" if is_review else "문법 학습"
    await send_message(chat_id, f"{label}을 시작합니다. 총 {len(items)}문항, 버튼으로 답해주세요.")
    await _send_grammar_question(chat_id, first)
    return True


async def _send_grammar_question(chat_id: int, question: grammar_service.GrammarQuestion) -> None:
    # 개념 설명을 문제보다 먼저 보여준다 (확인질문 없이 바로 이어서, 섹션7 학습자동화 원칙).
    if question.concept_intro:
        topic_label = f"[{question.topic}]\n" if question.topic else ""
        await send_message(chat_id, f"{topic_label}{question.concept_intro}")

    keyboard = build_inline_keyboard(
        [(choice, f"grammar:{question.question_id}:{idx}") for idx, choice in enumerate(question.choices)],
        columns=1,
    )
    prefix = f"[{question.topic}] " if question.topic else ""
    await send_message(chat_id, f"{prefix}{question.prompt}", reply_markup=keyboard)


async def _handle_grammar_answer(telegram_id: str, chat_id: int, question_id: int, choice_index: int) -> None:
    result = grammar_service.submit_answer(telegram_id, question_id, choice_index)
    if result is None:
        await send_message(
            chat_id,
            "이미 처리된 문항이거나 세션이 만료되었습니다.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    user = await users_repo.get_user_by_telegram_id(telegram_id)
    # 오답 유형은 별도 태그 체계 대신 문항의 topic을 그대로 기록 (섹션18 [결정필요])
    error_tag = None if result.is_correct else result.question.topic
    await grammar_repo.record_answer(user["id"], question_id, result.is_correct, error_tag, result.is_review)

    if result.is_correct:
        feedback = "정답입니다!"
    else:
        correct_choice = result.question.choices[result.question.correct_index]
        feedback = f"오답입니다. 정답: {correct_choice}"
        if result.question.explanation:
            feedback += f"\n해설: {result.question.explanation}"

    if not result.finished:
        await send_message(chat_id, feedback)
        await _send_grammar_question(chat_id, result.next_question)
        return

    if today_session.is_active(telegram_id) and not result.is_review:
        await learning_sessions_repo.mark_stage_complete(user["id"], "grammar")
        await send_message(chat_id, f"{feedback}\n\n문법 학습 완료! {result.total}문제 중 {result.correct}개 정답")
        await _advance_today_session(telegram_id, chat_id, user)
        return

    label = "복습" if result.is_review else "문법 학습"
    await send_message(
        chat_id,
        f"{feedback}\n\n{label} 완료! {result.total}문제 중 {result.correct}개 정답",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


async def _start_today_session(telegram_id: str, chat_id: int, user) -> None:
    await learning_sessions_repo.start_today(user["id"])
    today_session.start(telegram_id)

    weak_topics = await grammar_repo.get_weak_topics(user["id"], 3)
    if weak_topics:
        accuracy = await grammar_repo.get_overall_accuracy(user["id"])
        level = user["placement_level"] or "beginner"
        focus_message = await planner.build_focus_message(level, weak_topics, accuracy)
        if focus_message:
            await learning_sessions_repo.increment_ai_call_count(user["id"])
            await send_message(chat_id, f"📌 {focus_message}")

    await send_message(chat_id, "오늘의 학습을 시작합니다: 단어 학습 → 문법 학습 순서로 자동 진행됩니다.")
    started = await _start_vocab_session(telegram_id, chat_id, user)
    if not started:
        await _advance_today_session(telegram_id, chat_id, user)


async def _advance_today_session(telegram_id: str, chat_id: int, user) -> None:
    next_stage = today_session.advance(telegram_id)

    if next_stage == "grammar":
        started = await _start_grammar_session(telegram_id, chat_id, user, is_review=False)
        if not started:
            # 오늘 이미 문법 학습을 했거나 문제가 없으면 건너뛰고 오늘의 학습을 마무리한다.
            await _advance_today_session(telegram_id, chat_id, user)
        return

    if next_stage == "reading":
        started = await _start_reading_session(telegram_id, chat_id, user, is_review=False)
        if not started:
            await _advance_today_session(telegram_id, chat_id, user)
        return

    if next_stage == "conversation":
        started = await _start_conversation_session(telegram_id, chat_id, user)
        if not started:
            await _advance_today_session(telegram_id, chat_id, user)
        return

    # 더 이상 진행할 단계가 없음 (단어->문법->해석->회화 모두 완료 또는 스킵)
    await learning_sessions_repo.mark_completed(user["id"])
    await send_message(
        chat_id,
        "오늘의 학습을 모두 마쳤습니다! 수고하셨어요.",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


READING_MAX_ATTEMPTS = reading_service.MAX_ATTEMPTS


async def _start_reading_session(telegram_id: str, chat_id: int, user, is_review: bool) -> bool:
    level = user["placement_level"] or "beginner"
    row = await reading_repo.get_random_passage(level)
    if row is None:
        await send_message(
            chat_id,
            "아직 학습할 지문이 없습니다.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return False

    passage = reading_service.Passage(
        passage_id=row["id"],
        text=row["passage_text"],
        model_translation=row["model_translation_ko"],
        level=row["level"],
    )
    reading_service.start(telegram_id, passage, is_review)

    label = "복습" if is_review else "해석 학습"
    await send_message(
        chat_id,
        f"{label}을 시작합니다. 아래 지문을 읽고 한국어로 해석해서 보내주세요.\n\n{passage.text}",
    )
    return True


async def _handle_reading_answer(telegram_id: str, chat_id: int, user, text: str) -> None:
    session = reading_service.get_session(telegram_id)
    if session is None:
        return

    attempt = reading_service.record_attempt(telegram_id)

    try:
        is_adequate, feedback = await reading_evaluator.evaluate(session.passage.text, text)
    except Exception:
        logger.exception("reading evaluation failed")
        is_adequate, feedback = True, "채점 중 문제가 발생했습니다. 모범 번역과 비교해 보세요."

    await reading_repo.record_attempt(
        user["id"], session.passage.passage_id, text, feedback, attempt, is_adequate, session.is_review
    )

    finished = is_adequate or attempt >= READING_MAX_ATTEMPTS
    if not finished:
        await send_message(chat_id, f"{feedback}\n다시 한 번 해석해서 보내주세요.")
        return

    reading_service.finish(telegram_id)
    summary = f"{feedback}\n\n모범 번역: {session.passage.model_translation}"

    if today_session.is_active(telegram_id) and not session.is_review:
        await learning_sessions_repo.mark_stage_complete(user["id"], "reading")
        await send_message(chat_id, summary)
        await _advance_today_session(telegram_id, chat_id, user)
        return

    label = "복습" if session.is_review else "해석 학습"
    await send_message(
        chat_id,
        f"{summary}\n\n{label} 완료!",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


async def _start_conversation_session(telegram_id: str, chat_id: int, user) -> bool:
    already_done = user["role"] != "admin" and await conversation_repo.has_completed_today(user["id"])
    if already_done:
        await send_message(
            chat_id,
            "오늘의 회화 연습은 이미 완료했습니다. 내일 다시 시도해 주세요.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return False

    level = user["placement_level"] or "beginner"
    try:
        opening = await conversation_chat.generate_opening(level)
    except Exception:
        logger.exception("conversation opening failed")
        await send_message(
            chat_id,
            "회화 연습을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return False

    session_id = await conversation_repo.create_session(user["id"], level)
    await conversation_repo.add_message(session_id, "model", opening)
    conversation_service.start(telegram_id, level, session_id)
    conversation_service.add_ai_message(telegram_id, opening)

    await send_message(
        chat_id,
        f"💬 회화 연습을 시작합니다 (총 {conversation_service.MAX_TURNS}턴, 영어로 자유롭게 답해보세요).\n\n{opening}",
    )
    return True


async def _handle_conversation_message(telegram_id: str, chat_id: int, user, text: str) -> None:
    session = conversation_service.get_session(telegram_id)
    if session is None:
        return

    await conversation_repo.add_message(session.session_id, "user", text)

    try:
        ai_reply = await conversation_chat.generate_reply(session.level, session.history, text)
    except Exception:
        logger.exception("conversation reply failed")
        ai_reply = "Sorry, I had trouble responding just now. Let's continue — what do you think?"

    await conversation_repo.add_message(session.session_id, "model", ai_reply)
    turn_count = conversation_service.add_user_turn(telegram_id, text, ai_reply)

    if turn_count < conversation_service.MAX_TURNS:
        await send_message(chat_id, ai_reply)
        return

    conversation_service.finish(telegram_id)
    await conversation_repo.complete_session(session.session_id, turn_count)

    if today_session.is_active(telegram_id):
        await learning_sessions_repo.mark_stage_complete(user["id"], "conversation")
        await send_message(chat_id, f"{ai_reply}\n\n회화 연습 완료! 수고하셨어요.")
        await _advance_today_session(telegram_id, chat_id, user)
        return

    await send_message(
        chat_id,
        f"{ai_reply}\n\n회화 연습 완료! 수고하셨어요.",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


CUSTOM_TEXT_MAX_WORDS = 8
CUSTOM_TEXT_MIN_CHARS = 20


async def _start_custom_text_session(telegram_id: str, chat_id: int, user) -> None:
    level = user["placement_level"] or "beginner"
    custom_text_service.start(telegram_id, level)
    await send_message(chat_id, "학습할 영어 텍스트를 붙여넣어 주세요. (기사, 문단 등 자유롭게)")


async def _handle_custom_text_message(telegram_id: str, chat_id: int, user, text: str) -> None:
    session = custom_text_service.get_session(telegram_id)
    if session is None:
        return

    if session.stage == "awaiting_text":
        await _handle_custom_text_pasted(telegram_id, chat_id, user, session, text)
        return

    if session.stage == "awaiting_translation":
        await _handle_custom_text_translation(telegram_id, chat_id, user, session, text)
        return


async def _handle_custom_text_pasted(telegram_id: str, chat_id: int, user, session, text: str) -> None:
    if len(text.strip()) < CUSTOM_TEXT_MIN_CHARS:
        await send_message(chat_id, "텍스트가 너무 짧습니다. 조금 더 긴 문단을 붙여넣어 주세요.")
        return

    try:
        vocab_items = await custom_text_extractor.extract_key_vocabulary(text, session.level, CUSTOM_TEXT_MAX_WORDS)
    except Exception:
        logger.exception("custom text vocabulary extraction failed")
        vocab_items = []

    word_items: list[vocab_service.WordItem] = []
    if vocab_items:
        await content_repo.insert_words(session.level, vocab_items)
        id_map = await content_repo.get_word_ids([w["word"] for w in vocab_items])
        for w in vocab_items:
            word_id = id_map.get(w["word"])
            if word_id is None:
                continue
            word_items.append(
                vocab_service.WordItem(
                    word_id=word_id,
                    word=w["word"],
                    meaning_ko=w["meaning_ko"],
                    pronunciation=w.get("pronunciation"),
                    example_sentence=w.get("example_sentence"),
                    example_translation=w.get("example_translation"),
                    level=session.level,
                    ease=srs.INITIAL_EASE,
                    interval_days=srs.INITIAL_INTERVAL_DAYS,
                    is_new=True,
                )
            )

    custom_text_service.enter_cards_stage(telegram_id, text, len(word_items))

    if word_items:
        await send_message(chat_id, f"핵심 단어 {len(word_items)}개를 찾았어요. 카드로 확인해볼게요.")
        first = vocab_service.start_session(telegram_id, word_items)
        await _send_word_card(chat_id, first)
        return

    # 추출된 단어가 없으면(짧은 텍스트, 쉬운 어휘 등) 카드 단계를 건너뛰고 바로 해석 단계로.
    custom_text_service.enter_translation_stage(telegram_id)
    await send_message(chat_id, f"이제 전체 텍스트를 한국어로 해석해서 보내주세요.\n\n{text}")


async def _handle_custom_text_translation(telegram_id: str, chat_id: int, user, session, translation: str) -> None:
    try:
        feedback = await custom_text_feedback.generate_feedback(session.text, translation)
    except Exception:
        logger.exception("custom text feedback failed")
        feedback = "피드백 생성 중 문제가 발생했습니다. 그래도 텍스트 학습은 잘 하셨어요!"

    await custom_text_repo.save(user["id"], session.level, session.text, session.word_count, translation, feedback)
    custom_text_service.finish(telegram_id)

    await send_message(
        chat_id,
        f"{feedback}\n\n텍스트 붙여넣기 학습 완료! 추출된 단어 {session.word_count}개는 단어학습에서 다시 만나게 됩니다.",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


SCHOOL_ASSIGNMENT_MAX_WORDS = 8
SCHOOL_ASSIGNMENT_MIN_CHARS = 20
SCHOOL_ASSIGNMENT_EXAM_QUESTIONS = 3


def _d_day_label(exam_date) -> str:
    days = (exam_date - date.today()).days
    if days > 0:
        return f"D-{days}"
    if days == 0:
        return "D-DAY"
    return f"D+{-days}"


async def _start_school_assignment_session(telegram_id: str, chat_id: int, user) -> None:
    level = user["placement_level"] or "beginner"
    school_assignment_service.start(telegram_id, level)

    # 등록된 시험(M13)이 있으면 이 자료를 연결해 시험직전복습에서 오답을 다시 만날 수 있게 한다.
    exams = await school_exams_repo.list_upcoming(user["id"], date.today())
    if not exams:
        await send_message(chat_id, "학교 수행평가로 받은 영어 지문을 붙여넣어 주세요.")
        return

    if len(exams) == 1:
        exam = exams[0]
        school_assignment_service.set_exam_id(telegram_id, exam["id"])
        await send_message(
            chat_id,
            f"현재 등록된 시험 '{exam['subject']}'({_d_day_label(exam['exam_date'])}) 자료로 연결합니다.\n"
            f"학교 수행평가로 받은 영어 지문을 붙여넣어 주세요.",
        )
        return

    keyboard = build_inline_keyboard(
        [(f"{e['subject']} ({_d_day_label(e['exam_date'])})", f"schoolexamlink:{e['id']}") for e in exams]
        + [("연결 안함", "schoolexamlink:none")],
        columns=1,
    )
    await send_message(chat_id, "이 자료를 어떤 시험과 연결할까요?", reply_markup=keyboard)


async def _handle_school_assignment_exam_link(telegram_id: str, chat_id: int, exam_id: int | None) -> None:
    session = school_assignment_service.get_session(telegram_id)
    if session is None:
        return
    school_assignment_service.set_exam_id(telegram_id, exam_id)
    await send_message(chat_id, "학교 수행평가로 받은 영어 지문을 붙여넣어 주세요.")


async def _handle_school_assignment_pasted(telegram_id: str, chat_id: int, user, session, text: str) -> None:
    if len(text.strip()) < SCHOOL_ASSIGNMENT_MIN_CHARS:
        await send_message(chat_id, "지문이 너무 짧습니다. 조금 더 긴 글을 붙여넣어 주세요.")
        return

    try:
        vocab_items = await custom_text_extractor.extract_key_vocabulary(
            text, session.level, SCHOOL_ASSIGNMENT_MAX_WORDS
        )
    except Exception:
        logger.exception("school assignment vocabulary extraction failed")
        vocab_items = []

    word_items: list[vocab_service.WordItem] = []
    if vocab_items:
        await content_repo.insert_words(session.level, vocab_items)
        id_map = await content_repo.get_word_ids([w["word"] for w in vocab_items])
        for w in vocab_items:
            word_id = id_map.get(w["word"])
            if word_id is None:
                continue
            word_items.append(
                vocab_service.WordItem(
                    word_id=word_id,
                    word=w["word"],
                    meaning_ko=w["meaning_ko"],
                    pronunciation=w.get("pronunciation"),
                    example_sentence=w.get("example_sentence"),
                    example_translation=w.get("example_translation"),
                    level=session.level,
                    ease=srs.INITIAL_EASE,
                    interval_days=srs.INITIAL_INTERVAL_DAYS,
                    is_new=True,
                )
            )

    school_assignment_service.enter_cards_stage(telegram_id, text, len(word_items))

    if word_items:
        await send_message(chat_id, f"핵심 단어 {len(word_items)}개를 찾았어요. 카드로 확인해볼게요.")
        first = vocab_service.start_session(telegram_id, word_items)
        await _send_word_card(chat_id, first)
        return

    # 추출된 단어가 없으면(짧은 지문, 쉬운 어휘 등) 카드 단계를 건너뛰고 바로 문법해설/예상문제 단계로.
    await _start_school_assignment_exam(telegram_id, chat_id, user, session.level, text)


async def _start_school_assignment_exam(telegram_id: str, chat_id: int, user, level: str, text: str) -> None:
    try:
        analysis = await school_assignment_analyzer.analyze(text, level, SCHOOL_ASSIGNMENT_EXAM_QUESTIONS)
    except Exception:
        logger.exception("school assignment analysis failed")
        analysis = {"grammar_explanation": "", "questions": []}

    if analysis["grammar_explanation"]:
        await send_message(chat_id, f"📘 핵심 문법 해설\n{analysis['grammar_explanation']}")

    questions = [
        school_assignment_service.ExamQuestion(
            index=i,
            question=q["question"],
            choices=q["choices"],
            correct_index=q["correct_index"],
            explanation=q.get("explanation"),
        )
        for i, q in enumerate(analysis["questions"])
    ]

    session = school_assignment_service.get_session(telegram_id)
    word_count = session.word_count if session else 0
    exam_id = session.exam_id if session else None

    if not questions:
        await school_assignment_repo.save(
            user["id"], level, text, word_count, analysis["grammar_explanation"], 0, 0, exam_id=exam_id
        )
        school_assignment_service.finish(telegram_id)
        await send_message(
            chat_id,
            "예상 시험문제 생성에 실패했습니다. 문법 해설까지는 완료되었어요. 학교 수행평가 학습 완료!",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    school_assignment_service.enter_exam_stage(telegram_id, analysis["grammar_explanation"], questions)
    await send_message(chat_id, f"이제 예상 시험문제 {len(questions)}문항을 풀어볼까요? 버튼으로 답해주세요.")
    await _send_school_assignment_question(chat_id, questions[0])


async def _send_school_assignment_question(chat_id: int, question: school_assignment_service.ExamQuestion) -> None:
    keyboard = build_inline_keyboard(
        [(choice, f"examquiz:{question.index}:{idx}") for idx, choice in enumerate(question.choices)],
        columns=1,
    )
    await send_message(chat_id, f"[예상문제 {question.index + 1}] {question.question}", reply_markup=keyboard)


async def _handle_school_assignment_exam_answer(
    telegram_id: str, chat_id: int, question_index: int, choice_index: int
) -> None:
    question = school_assignment_service.current_question(telegram_id)
    if question is None:
        return

    result = school_assignment_service.submit_exam_answer(telegram_id, question_index, choice_index)
    if result is None:
        await send_message(
            chat_id,
            "이미 처리된 문항이거나 세션이 만료되었습니다.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    if result.is_correct:
        feedback = "정답입니다!"
    else:
        feedback = f"오답입니다. 정답: {question.choices[question.correct_index]}"
        if question.explanation:
            feedback += f"\n해설: {question.explanation}"

    if not result.finished:
        await send_message(chat_id, feedback)
        await _send_school_assignment_question(chat_id, result.next_question)
        return

    user = await users_repo.get_user_by_telegram_id(telegram_id)
    finished_session = school_assignment_service.finish(telegram_id)
    await school_assignment_repo.save(
        user["id"],
        finished_session.level,
        finished_session.text,
        finished_session.word_count,
        finished_session.grammar_explanation,
        result.total,
        result.correct,
        exam_id=finished_session.exam_id,
        question_details=finished_session.question_details(),
    )

    await send_message(
        chat_id,
        f"{feedback}\n\n학교 수행평가 학습 완료! 예상 시험문제 {result.total}문제 중 {result.correct}개 정답",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


async def _send_school_exam_menu(chat_id: int, is_admin: bool) -> None:
    await send_message(
        chat_id,
        "📅 시험관리\n"
        "/시험등록 - 과목/날짜/단원/선생님강조사항 등록\n"
        "/시험목록 - 등록된 시험 목록 (D-Day)\n"
        "/시험직전복습 - 연결된 자료의 오답만 다시 풀기",
        reply_markup=menu.build_main_menu_keyboard(is_admin),
    )


EXAM_DATE_FORMAT_HINT = "예: 2026-09-20"


async def _start_exam_registration(telegram_id: str, chat_id: int) -> None:
    exam_registration_service.start(telegram_id)
    await send_message(chat_id, "등록할 시험의 과목명을 입력해 주세요. (예: 영어)")


async def _handle_exam_registration_message(telegram_id: str, chat_id: int, user, session, text: str) -> None:
    text = text.strip()

    if session.stage == "subject":
        if not text:
            await send_message(chat_id, "과목명을 입력해 주세요.")
            return
        exam_registration_service.set_subject(telegram_id, text)
        await send_message(chat_id, f"시험 날짜를 입력해 주세요. ({EXAM_DATE_FORMAT_HINT})")
        return

    if session.stage == "date":
        try:
            exam_date = date.fromisoformat(text)
        except ValueError:
            await send_message(chat_id, f"날짜 형식이 올바르지 않습니다. ({EXAM_DATE_FORMAT_HINT})")
            return
        exam_registration_service.set_date(telegram_id, exam_date.isoformat())
        await send_message(chat_id, "시험 범위(단원)를 입력해 주세요. (예: 3~5단원, 부정사)")
        return

    if session.stage == "unit":
        exam_registration_service.set_unit(telegram_id, text)
        await send_message(chat_id, "선생님이 강조하신 부분이 있다면 입력해 주세요. (없으면 '없음'으로 입력)")
        return

    if session.stage == "teacher_notes":
        teacher_notes = "" if text in ("없음", "없어요", "-") else text
        finished = exam_registration_service.finish(telegram_id)
        exam_date = date.fromisoformat(finished.exam_date)
        await school_exams_repo.create(user["id"], finished.subject, exam_date, finished.unit_info, teacher_notes)
        await send_message(
            chat_id,
            f"시험이 등록되었습니다!\n📚 {finished.subject} ({_d_day_label(exam_date)})\n"
            f"범위: {finished.unit_info}\n선생님 강조: {teacher_notes or '없음'}\n\n"
            f"/수행평가로 이 시험 관련 자료를 붙여넣으면 자동으로 연결됩니다.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return


async def _handle_exam_list(telegram_id: str, chat_id: int, user) -> None:
    exams = await school_exams_repo.list_all(user["id"])
    if not exams:
        await send_message(
            chat_id,
            "등록된 시험이 없습니다. /시험등록으로 등록해 주세요.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    lines = ["📅 등록된 시험 목록"]
    for exam in exams:
        lines.append(
            f"- {exam['subject']} ({_d_day_label(exam['exam_date'])}) | 범위: {exam['unit_info'] or '-'} "
            f"| 선생님강조: {exam['teacher_notes'] or '없음'}"
        )
    await send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


async def _start_exam_review(telegram_id: str, chat_id: int, user) -> None:
    exams = await school_exams_repo.list_upcoming(user["id"], date.today())
    if not exams:
        await send_message(
            chat_id,
            "등록된 예정 시험이 없습니다. /시험등록으로 먼저 등록해 주세요.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    if len(exams) == 1:
        await _begin_exam_review_for(telegram_id, chat_id, user, exams[0])
        return

    keyboard = build_inline_keyboard(
        [(f"{e['subject']} ({_d_day_label(e['exam_date'])})", f"examreviewpick:{e['id']}") for e in exams],
        columns=1,
    )
    await send_message(chat_id, "어떤 시험을 복습할까요?", reply_markup=keyboard)


async def _handle_exam_review_pick(telegram_id: str, chat_id: int, exam_id: int) -> None:
    user = await users_repo.get_user_by_telegram_id(telegram_id)
    exam = await school_exams_repo.get_by_id(exam_id, user["id"])
    if exam is None:
        return
    await _begin_exam_review_for(telegram_id, chat_id, user, exam)


async def _begin_exam_review_for(telegram_id: str, chat_id: int, user, exam) -> None:
    lines = [f"📌 {exam['subject']} ({_d_day_label(exam['exam_date'])}) 시험직전복습"]
    if exam["unit_info"]:
        lines.append(f"범위: {exam['unit_info']}")
    if exam["teacher_notes"]:
        lines.append(f"선생님 강조: {exam['teacher_notes']}")
    await send_message(chat_id, "\n".join(lines))

    wrong_questions = await school_assignment_repo.get_wrong_questions_for_exam(user["id"], exam["id"])
    if not wrong_questions:
        await send_message(
            chat_id,
            "아직 다시 볼 오답이 없어요. /수행평가로 이 시험 관련 자료를 먼저 학습해 보세요.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    questions = [
        school_assignment_service.ExamQuestion(
            index=i,
            question=q["question"],
            choices=q["choices"],
            correct_index=q["correct_index"],
            explanation=q.get("explanation"),
        )
        for i, q in enumerate(wrong_questions)
    ]
    exam_review_service.start(telegram_id, exam["id"], questions)
    await send_message(chat_id, f"오답 {len(questions)}문항을 다시 풀어볼까요? 버튼으로 답해주세요.")
    await _send_exam_review_question(chat_id, questions[0])


async def _send_exam_review_question(chat_id: int, question: school_assignment_service.ExamQuestion) -> None:
    keyboard = build_inline_keyboard(
        [(choice, f"examreviewquiz:{question.index}:{idx}") for idx, choice in enumerate(question.choices)],
        columns=1,
    )
    await send_message(chat_id, f"[복습 {question.index + 1}] {question.question}", reply_markup=keyboard)


async def _handle_exam_review_answer(telegram_id: str, chat_id: int, question_index: int, choice_index: int) -> None:
    question = exam_review_service.current_question(telegram_id)
    if question is None:
        return

    result = exam_review_service.submit_answer(telegram_id, question_index, choice_index)
    if result is None:
        await send_message(
            chat_id,
            "이미 처리된 문항이거나 세션이 만료되었습니다.",
            reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
        )
        return

    if result.is_correct:
        feedback = "정답입니다!"
    else:
        feedback = f"오답입니다. 정답: {question.choices[question.correct_index]}"
        if question.explanation:
            feedback += f"\n해설: {question.explanation}"

    if not result.finished:
        await send_message(chat_id, feedback)
        await _send_exam_review_question(chat_id, result.next_question)
        return

    finished_session = exam_review_service.finish(telegram_id)
    user = await users_repo.get_user_by_telegram_id(telegram_id)
    await school_exams_repo.record_review(finished_session.exam_id, user["id"], result.total, result.correct)

    await send_message(
        chat_id,
        f"{feedback}\n\n시험직전복습 완료! {result.total}문제 중 {result.correct}개 정답. 시험 잘 보세요!",
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )


async def _handle_admin_approve(chat_id: int, text: str) -> None:
    parts = text.split()
    if len(parts) != 2:
        await send_message(chat_id, "사용법: /승인 <telegram_id> (또는 /approve <telegram_id>)")
        return

    target_id = parts[1]
    await users_repo.approve_user(target_id)
    await send_message(chat_id, f"{target_id} 승인 완료")
    await send_message(target_id, "승인되었습니다! /start 를 다시 입력해 주세요.")


async def _handle_admin_list_pending(chat_id: int) -> None:
    pending = await users_repo.list_pending_users()
    if not pending:
        await send_message(chat_id, "대기 중인 사용자가 없습니다.")
        return

    lines = [f"- {row['telegram_id']} (등록: {row['created_at']})" for row in pending]
    await send_message(chat_id, "승인 대기 목록:\n" + "\n".join(lines))


async def _handle_admin_list_users(chat_id: int) -> None:
    rows = await users_repo.list_approved_users_with_activity()
    if not rows:
        await send_message(chat_id, "승인된 사용자가 없습니다.")
        return

    lines = []
    for row in rows:
        role_tag = " [관리자]" if row["role"] == "admin" else ""
        age = f"{row['age']}세" if row["age"] is not None else "나이미입력"
        mode = row["learning_mode"] or "모드미배정"
        level = row["placement_level"] or "레벨미진단"
        last_active = row["last_active_at"].strftime("%Y-%m-%d %H:%M") if row["last_active_at"] else "-"
        lines.append(
            f"- {row['telegram_id']}{role_tag} | {age} | {mode}/{level} "
            f"| 오늘 활동 {row['today_activity_count']}회 | 최근접속 {last_active}"
        )
    await send_message(chat_id, f"사용자 목록 ({len(rows)}명):\n" + "\n".join(lines))


async def _handle_progress(telegram_id: str, chat_id: int, user) -> None:
    word_counts = await user_words_repo.get_progress_counts(user["id"])
    known = word_counts.get("known", 0)
    learning = word_counts.get("learning", 0)

    grammar_accuracy = await grammar_repo.get_overall_accuracy(user["id"])
    weak_topics = await grammar_repo.get_weak_topics(user["id"], 3)

    reading_stats = await reading_repo.get_progress_stats(user["id"])
    conversation_count = await conversation_repo.get_completed_session_count(user["id"])

    lines = [f"📊 진도 확인 — 레벨: {user['placement_level'] or '미진단'}", ""]
    lines.append(f"📚 단어: 완전히 익힘 {known}개, 학습중 {learning}개")

    if grammar_accuracy is not None:
        lines.append(f"✍️ 문법: 정답률 {grammar_accuracy:.0%}")
    else:
        lines.append("✍️ 문법: 아직 학습 기록 없음")
    if weak_topics:
        lines.append(f"   취약 주제: {', '.join(weak_topics)}")

    if reading_stats["total"]:
        lines.append(f"📖 해석: {reading_stats['total']}회 시도, 적절 판정 {reading_stats['adequate']}회")
    else:
        lines.append("📖 해석: 아직 학습 기록 없음")

    lines.append(f"💬 회화: 완료한 세션 {conversation_count}회")

    await send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=menu.build_main_menu_keyboard(telegram_id == settings.admin_telegram_id),
    )
