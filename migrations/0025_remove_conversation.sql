-- 대규모 방향 전환(2026-09): 회화(Conversation) 기능을 완전히 제거하고 문법 학습에 리소스를
-- 집중한다. topic_words(과거 conversation_topic_words, 0024에서 이름 변경됨)는 단어학습/해석이
-- 계속 공유하므로 그대로 둔다 — 여기서 지우는 것은 회화 전용 테이블/컬럼뿐이다.
drop table if exists conversation_messages;
drop table if exists conversation_sessions;

alter table users drop column if exists conversation_level;
