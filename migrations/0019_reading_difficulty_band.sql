-- 개인 맞춤 난이도 시스템 3/4: 독해 — 지문별 난이도 메타데이터 + 사용자별 적응 밴드.
alter table reading_passages add column if not exists avg_sentence_length integer;
alter table reading_passages add column if not exists vocab_level text;
alter table reading_passages add column if not exists grammar_complexity text;
-- difficulty_band: 0(쉬움)~5(어려움), 위 메타데이터를 종합해 AI가 생성 시점에 함께 매긴 값.
-- 실제 지문 선택/적응 조정은 이 단일 축으로 이뤄진다(단어의 frequency_rank 밴드와 동일한 방식).
alter table reading_passages add column if not exists difficulty_band integer;
create index if not exists idx_reading_passages_band on reading_passages (difficulty_band);

alter table users add column if not exists reading_band integer not null default 0;
