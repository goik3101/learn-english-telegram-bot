-- M14: CHILD_BRIDGE 모드
-- 콘텐츠뱅크(words/grammar_questions/reading_passages)를 학습모드별로 분리해,
-- 같은 레벨이라도 11세에게 맞는 톤/난이도의 콘텐츠를 GENERAL(성인용)과 독립적으로 보관한다.
-- 기존 행은 전부 GENERAL로 취급(하위호환).
alter table words add column if not exists learning_mode text not null default 'GENERAL';
alter table grammar_questions add column if not exists learning_mode text not null default 'GENERAL';
alter table reading_passages add column if not exists learning_mode text not null default 'GENERAL';

-- 같은 단어라도 모드별로 별도 콘텐츠를 가질 수 있어야 하므로 유일성 범위를 (word, learning_mode)로 조정.
alter table words drop constraint if exists words_word_key;
alter table words add constraint words_word_mode_key unique (word, learning_mode);

create index if not exists idx_words_mode_level on words (learning_mode, level);
create index if not exists idx_grammar_questions_mode_level on grammar_questions (learning_mode, level);
create index if not exists idx_reading_passages_mode_level on reading_passages (learning_mode, level);
