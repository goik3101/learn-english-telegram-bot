-- 사용자 버그리포트 반영:
-- 1) 문법 커리큘럼을 배치레벨별 3개 목록에서 전역 단일 순서로 바꾸면서(app/grammar/curriculum.py),
--    기존 grammar_topic_index의 의미가 완전히 달라진다(같은 숫자가 이제 다른 주제를 가리킴).
--    잘못된 주제로 착각해 게이팅이 깨지는 것을 막기 위해 전원 0으로 리셋한다 — 숙달기준(정답률
--    80%/최소10문제)만 통과하면 빠르게 다시 그 위치까지 올라오므로 실질적 손해는 크지 않다.
update users set grammar_topic_index = 0;

-- 2) 단어 암기 효율 개선: 연상법(mnemonic) + 복습 회차마다 다른 예문을 보여주기 위한 예문 여러 개.
--    기존 example_sentence/example_translation 단일 컬럼은 그대로 두고(과거 데이터/다른 생성
--    경로와 호환), 새 콘텐츠부터 채워지는 보조 컬럼만 추가한다. review_count는 복습 때마다 예문을
--    순환시키기 위한 카운터.
alter table words add column if not exists mnemonic text;
alter table words add column if not exists example_sentences jsonb;
alter table user_words add column if not exists review_count integer not null default 0;
