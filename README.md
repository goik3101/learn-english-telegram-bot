# AI 개인 맞춤 영어학습 텔레그램 봇

기획서(V2)에 따른 관리자 승인 기반 소수 사용자용 텔레그램 영어학습 봇. 진행 상황은 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) 참고.

## 1. 로컬 개발 환경 준비

```bash
python -m venv .venv
./.venv/Scripts/activate   # Windows
pip install -r requirements-dev.txt
```

`.env.example`을 복사해 `.env`를 만들고 값을 채운다.

```bash
cp .env.example .env
```

### 필요한 외부 계정/키 (아직 없다면 아래 순서로 준비)

1. **Telegram Bot Token**
   - Telegram에서 `@BotFather`에게 `/newbot` 전송 → 봇 이름 설정 → 발급된 토큰을 `.env`의 `BOT_TOKEN`에 저장.
2. **관리자 Telegram ID**
   - `@userinfobot`에게 아무 메시지나 보내면 본인의 숫자 ID를 알려줌 → `.env`의 `ADMIN_TELEGRAM_ID`에 저장.
3. **Supabase 프로젝트 (Postgres)**
   - [supabase.com](https://supabase.com)에서 무료 프로젝트 생성 → 프로젝트 메인 화면 상단의 **"Connect"** 버튼 → **"Session pooler"** 탭에서 URI 복사 (형태: `postgres://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`).
   - ⚠️ **"Direct connection string"**(`db.<project-ref>.supabase.co`)은 무료 티어에서 IPv6 전용이라 대부분의 로컬/일반 네트워크에서 연결이 안 된다. 반드시 **Session pooler**(IPv4)를 사용할 것.
   - 비밀번호를 모르면 같은 화면 근처에서 "Reset database password"로 재설정.
4. **Gemini API Key**
   - [Google AI Studio](https://aistudio.google.com/apikey)에서 무료 API 키 발급 → `.env`의 `GEMINI_API_KEY`에 저장.
   - ⚠️ 최신 모델(`gemini-3.6-flash` 등)은 아직 표준 무료 티어(하루 1,500회)를 받지 못하고 도입 초기 할당량(하루 20회)만 제공되는 경우가 있다 — 실측으로 확인함. 이 프로젝트는 같은 세대의 **`gemini-3.1-flash-lite`**(표준 무료 티어 포함)를 기본 모델로 사용해 이 문제를 피했다(`app/ai/gemini_client.py`). 무료 티어 할당량은 모델별로 독립적이니, 나중에 더 최신 모델로 바꾸고 싶다면 먼저 실제로 호출해서 한도를 확인해볼 것. 자세한 내용은 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)의 M9 항목 참고.
5. **Railway (배포, 나중에)**
   - 로컬 개발이 끝난 뒤 Railway 프로젝트를 만들어 이 저장소를 연결하고 위 환경변수를 그대로 등록.

키가 하나도 없어도 서버는 정상 기동하며(경고 로그만 출력), `DATABASE_URL` 없이는 실제 사용자 데이터 처리는 동작하지 않는다.

## 2. DB 마이그레이션 적용

`migrations/` 아래 SQL 파일을 번호 순서대로 Supabase SQL Editor(또는 `psql`)에서 실행한다.

```bash
psql "$DATABASE_URL" -f migrations/0001_init_users.sql
psql "$DATABASE_URL" -f migrations/0002_placement_test_results.sql
psql "$DATABASE_URL" -f migrations/0003_content_bank.sql
psql "$DATABASE_URL" -f migrations/0004_user_words.sql
psql "$DATABASE_URL" -f migrations/0005_user_grammar_answers.sql
psql "$DATABASE_URL" -f migrations/0006_grammar_concept_intro.sql
psql "$DATABASE_URL" -f migrations/0007_learning_sessions.sql
psql "$DATABASE_URL" -f migrations/0008_reading.sql
psql "$DATABASE_URL" -f migrations/0009_conversation.sql
psql "$DATABASE_URL" -f migrations/0010_custom_texts.sql
psql "$DATABASE_URL" -f migrations/0011_school_assignment.sql
```

## 3-1. 단어/문법/해석 콘텐츠뱅크 생성 (M4/M8, 1회성)

Gemini로 레벨별 단어/문법 문항/해석 지문을 대량 생성해 `words`/`grammar_questions`/`reading_passages` 테이블에 채운다. 실시간 사용자 요청이 아니라 사전 준비 작업이라 별도 스크립트로 실행한다.

```bash
python scripts/generate_content_bank.py --words-per-level 15 --grammar-per-level 10 --reading-per-level 5
```

단어는 중복이면 자동으로 스킵되므로, 콘텐츠가 부족해지면 몇 번이고 다시 실행해 채워 넣을 수 있다.

## 3. 로컬 서버 실행

**Windows**에서는 `uvicorn` CLI를 직접 쓰지 말고 아래 스크립트를 사용한다 — psycopg 비동기 모드가 Windows 기본 이벤트루프(ProactorEventLoop)를 지원하지 않아서, 이벤트루프가 만들어지기 전에 정책을 바꿔주는 래퍼가 필요하다 (Linux/Railway 배포 환경에는 이 이슈가 없음).

```bash
python run_local.py
```

Linux/Mac 또는 배포 환경에서는 그냥:

```bash
uvicorn app.main:app --reload --port 8000
```

- `GET /health` — 헬스체크
- `POST /telegram/webhook` — 텔레그램 업데이트 수신

## 4. 로컬에서 실제 텔레그램으로 테스트하기

**방법 A — ngrok 없이 (권장, 로컬 개발용)**: webhook 대신 long polling으로 실제 텔레그램과 대화한다.

```bash
python scripts/poll_dev.py
```

실행 중인 동안 텔레그램 앱에서 봇에게 메시지를 보내면 실시간으로 처리된다. (webhook이 등록되어 있으면 getUpdates가 실패하므로, 이 방식을 쓸 때는 `set_webhook.py`로 webhook을 등록한 적이 없어야 한다.)

**방법 B — ngrok (배포와 동일한 webhook 방식을 테스트하고 싶을 때)**:

```bash
ngrok http 8000
python scripts/set_webhook.py https://<ngrok-subdomain>.ngrok-free.app
```

이후 실제 텔레그램 앱에서 봇에게 `/start`를 보내면 동작을 확인할 수 있다.

## 5. 테스트

```bash
pytest
```

현재는 DB/텔레그램/Gemini API를 모킹한 로직 테스트만 있다 — 승인 플로우/나이→모드 배정(`tests/test_router.py`), 레벨진단 전체 플로우(`tests/test_placement_flow.py`), 콘텐츠 생성 응답 검증(`tests/test_content_generator.py`), 단어학습/SRS/단어시험(`tests/test_vocab_flow.py`, `tests/test_vocab_quiz.py`), 문법학습/오답기록(`tests/test_grammar_flow.py`), 메인 메뉴/메시지 정리(`tests/test_menu.py`).

## 6. 메인 메뉴 & 사용자 명령어

최초 온보딩(나이입력→레벨진단) 완료 후에는 버튼 기반 메인 메뉴가 뜬다 — 명령어를 몰라도 버튼으로 대부분 조작 가능:

모든 GENERAL 모드 메뉴 버튼이 구현되어 있다: 🗓 오늘의 학습, 📚 단어 학습, 🔤 단어 시험, ✍️ 문법 학습, 🔁 복습, 📖 해석(Reading), 💬 회화(Conversation), 📄 텍스트 붙여넣기 학습, 📝 학교 수행평가, 📊 진도 확인.

명령어는 한글/영문 둘 다 인식한다. 영문 명령어는 텔레그램 채팅창에 `/`만 입력해도 자동완성 목록으로 뜬다(한글 명령어는 텔레그램 규칙상 자동완성 등록이 안 돼서 직접 타이핑만 가능):

| 한글 | 영문 | 설명 |
|---|---|---|
| `/메뉴` | `/menu` | 메뉴를 언제든 다시 표시 |
| `/start` | `/start` | 최초 접속(승인대기 등록) / 나이입력 / 레벨진단 시작 / 재접속 시 메뉴 표시 |
| `/오늘학습` | `/todaylearning` | 단어 학습 → 문법 학습 → 해석 학습 → 회화 학습을 확인질문 없이 자동으로 이어서 진행. 최근 문법 오답 데이터가 있으면 시작 전 AI가 만든 짧은 포커스 메시지를 먼저 보여줌 |
| `/레벨진단` | `/leveltest` | GENERAL·CHILD_BRIDGE 모드 사용자가 언제든 재응시 가능 |
| `/단어학습` | `/vocabstudy` | 오늘의 복습 대상 + 신규 단어를 카드로 학습 (아는단어/모르는단어→객관식→주관식) |
| `/단어시험` | `/vocabquiz` | 이미 학습한 단어 샘플로 객관식 반복 테스트 (SRS에 영향 없음) |
| `/문법학습` | `/grammarstudy` | 개념 설명 → 문법 객관식 5문항, 정답/오답 자동 기록, 신규 세트는 하루 1회 |
| `/복습` | `/review` | 문법 문제를 제한 없이 반복 (현재는 문법만 지원) |
| `/해석` | `/reading` | 지문을 직접 해석해서 보내면 AI가 채점. **정답을 바로 안 알려주고 최대 2회까지 힌트만 제공**, 그 다음에 모범번역 공개. 언제든 반복 가능(하루 제한 없음) |
| `/회화` | `/conversation` | AI와 텍스트로 5턴 영어 대화. 레벨에 맞춰 난이도 조정. 신규 세트는 하루 1회 |
| `/진도` | `/progress` | 레벨/단어/문법/해석/회화 학습 현황을 한 화면에 요약 |
| `/텍스트학습` | `/customtext` | 원하는 영어 텍스트를 붙여넣으면 핵심 단어 카드 학습 → 전체 해석 → AI 피드백까지 진행. 추출된 단어는 단어뱅크에 합류해 이후 단어학습에서 다시 만남. 하루 제한 없음 |
| `/수행평가` | `/schooltask` | 학교 수행평가로 받은 지문을 붙여넣으면 핵심 단어 카드 학습 → 핵심 문법 해설 → 예상 시험문제 3문항(객관식)까지 진행. 하루 제한 없음 |

관리자 계정(`role=admin`)은 문법학습/회화의 "하루 1회" 제한을 받지 않는다(일반 사용자에게만 적용).

버튼이 달린 카드/문제 메시지는 답변 즉시 채팅에서 삭제되어(`deleteMessage`), 이미 답한 카드가 계속 남아 헷갈리는 일이 없다. (DB에 저장된 학습 기록에는 영향 없음 — 화면 정리만 한다.)

문법 학습 문제 문장에서 뽑은 핵심 단어는 자동으로 단어뱅크에 합류되어, 이후 단어학습에서 자연스럽게 만나게 된다(사용자 요청 반영, 별도 사용자별 AI 호출 없음).

## 7. 관리자 명령어

- ⚙️ 관리자 버튼 (관리자 계정에만 메뉴에 노출) — 사용 가능한 관리자 명령어 안내
- `/승인 <telegram_id>` (`/approve <telegram_id>`) — 승인 대기 사용자 승인
- `/대기목록` (`/pending`) — 승인 대기 중인 사용자 목록 조회
- `/사용자목록` (`/users`) — 승인된 전체 사용자의 아이디/나이/학습모드·레벨/오늘 활동 횟수/최근접속 조회

관리자 전용 명령어는 관리자의 텔레그램 채팅에만 `/` 자동완성으로 노출되고, 관리자 텔레그램 ID가 아니면 직접 입력해도 실행되지 않는다.

관리자 본인(`ADMIN_TELEGRAM_ID`)은 최초 `/start` 시 자동으로 승인/`role=admin` 처리된다.

## 8. 프로젝트 구조

```
app/
  main.py               FastAPI 앱, webhook 엔트리포인트
  config.py             환경변수 설정
  db.py                 Postgres 커넥션 풀 (psycopg3)
  telegram_client.py    Telegram Bot API 호출 (메시지, 인라인 키보드, 콜백 응답)
  modes.py              나이 -> 학습모드 매핑
  ai/gemini_client.py   Gemini API 래퍼 (텍스트 + JSON 구조화 응답)
  placement/            레벨진단(M3) 문항뱅크 + 세션/채점 로직
  content/generator.py  단어/문법 콘텐츠 AI 생성 + 응답 검증 (M4)
  srs.py                간격반복(SRS) 계산 + 신규단어 수 자동조절 (M5, 섹션14)
  vocab/service.py       단어학습/단어시험 세션 상태 관리 (M5)
  vocab/quiz.py           객관식 선택지 구성 + 주관식 유사도 채점 (M5)
  grammar/service.py      문법학습 세션 상태 관리 (M6)
  today_session.py        오늘의 학습(M7) 단계 진행 상태 (단어→문법→해석→회화 자동 체이닝)
  planner.py               Planner AI 보정 — 오답 데이터 기반 포커스 메시지 생성 (M7)
  reading/service.py       해석학습 세션 상태 관리 (M8)
  reading/evaluator.py     AI 채점 — 정답 대신 힌트 생성 (M8)
  conversation/service.py  회화학습 세션 상태 관리 (M9)
  conversation/chat.py     AI 대화 생성 (오프닝/턴별 응답) (M9)
  custom_text/service.py   텍스트붙여넣기 학습 세션 상태 관리 (M11)
  custom_text/extractor.py 붙여넣은 텍스트에서 핵심 단어 추출 (M11)
  custom_text/feedback.py  전체 해석에 대한 AI 피드백 생성 (M11)
  school_assignment/service.py  학교 수행평가 학습 세션 상태 관리 (M12)
  school_assignment/analyzer.py 지문의 핵심 문법 해설 + 예상 시험문제 생성 (M12)
  menu.py                메인 메뉴(리플라이 키보드) + 명령어 목록 구성
  commands.py             텔레그램 '/' 자동완성 명령어 등록
  repo/users.py          users 테이블 데이터 접근 (관리자 사용자목록 포함, M10)
  repo/placement.py      placement_test_results 데이터 접근
  repo/content.py        words/grammar_questions/reading_passages 데이터 접근
  repo/user_words.py      user_words(SRS) 데이터 접근
  repo/grammar.py         user_grammar_answers 데이터 접근 (M6)
  repo/learning_sessions.py user_id/날짜별 오늘의 학습 세션 기록 (M7)
  repo/reading.py          reading_passages/user_reading_attempts 데이터 접근 (M8)
  repo/conversation.py     conversation_sessions/conversation_messages 데이터 접근 (M9)
  repo/custom_text.py      custom_texts 데이터 접근 (M11)
  repo/school_assignment.py school_assignments 데이터 접근 (M12)
  handlers/router.py     업데이트 라우팅 (승인/나이입력/모드분기/레벨진단/단어학습/문법학습/해석학습/회화학습/텍스트학습/학교수행평가/오늘의학습/메뉴/콜백쿼리)
migrations/                    SQL 마이그레이션 (마일스톤 순서대로 번호 부여)
run_local.py                   Windows 로컬 서버 실행 래퍼 (이벤트루프 이슈 해결)
scripts/set_webhook.py         Telegram webhook 등록 스크립트
scripts/poll_dev.py            로컬 개발용 getUpdates 폴링 테스트 스크립트
scripts/generate_content_bank.py 단어/문법/해석 콘텐츠뱅크 생성 스크립트
scripts/enrich_existing_grammar.py 기존 문법 문제에 개념설명/핵심단어 소급 추가 (1회성)
scripts/simulate_today_session.py 오늘의학습 전체 플로우 자동 시뮬레이션 (수동 클릭 없이 검증용)
scripts/simulate_reading.py    해석학습 전체 플로우 자동 시뮬레이션 (수동 클릭 없이 검증용)
scripts/simulate_conversation.py 회화학습 전체 플로우 자동 시뮬레이션 (수동 클릭 없이 검증용)
scripts/simulate_custom_text.py 텍스트붙여넣기 학습 전체 플로우 자동 시뮬레이션 (수동 클릭 없이 검증용)
scripts/simulate_school_assignment.py 학교 수행평가 학습 전체 플로우 자동 시뮬레이션 (수동 클릭 없이 검증용)
scripts/apply_migration.py     psql 없는 로컬 환경에서 마이그레이션 SQL 파일을 실제 DB에 적용 (1회성)
tests/                  pytest 테스트
```
