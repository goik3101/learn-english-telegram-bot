-- M8: 해석(Reading) 지문 콘텐츠뱅크 + 사용자 시도 기록
create table if not exists reading_passages (
    id                    bigserial primary key,
    level                 text not null,
    passage_text          text not null,
    model_translation_ko  text not null,
    created_at            timestamptz not null default now()
);

create index if not exists idx_reading_passages_level on reading_passages (level);

create table if not exists user_reading_attempts (
    id                bigserial primary key,
    user_id           bigint not null references users (id) on delete cascade,
    passage_id        bigint not null references reading_passages (id) on delete cascade,
    user_translation  text not null,
    ai_feedback       text,
    attempt_number    integer not null,
    is_adequate       boolean not null,
    is_review         boolean not null default false,
    attempted_at      timestamptz not null default now()
);

create index if not exists idx_user_reading_attempts_user on user_reading_attempts (user_id);
