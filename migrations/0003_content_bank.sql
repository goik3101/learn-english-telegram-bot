-- M4: 단어/문법 콘텐츠뱅크 (AI로 사전 생성해 채워넣는 대상 테이블)
create table if not exists words (
    id                   bigserial primary key,
    word                 text not null unique,
    meaning_ko           text not null,
    part_of_speech       text,
    pronunciation        text,
    example_sentence     text,
    example_translation  text,
    level                text not null,  -- 'beginner' | 'intermediate' | 'advanced' (레벨진단과 동일 체계)
    created_at           timestamptz not null default now()
);

create index if not exists idx_words_level on words (level);

create table if not exists grammar_questions (
    id              bigserial primary key,
    level           text not null,
    topic           text,
    prompt          text not null,
    choices         jsonb not null,
    correct_index   integer not null,
    explanation     text,
    created_at      timestamptz not null default now()
);

create index if not exists idx_grammar_questions_level on grammar_questions (level);
