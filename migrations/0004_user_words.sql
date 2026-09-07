-- M5: 단어학습 SRS 진행상태
create table if not exists user_words (
    id                bigserial primary key,
    user_id           bigint not null references users (id) on delete cascade,
    word_id           bigint not null references words (id) on delete cascade,
    status            text not null default 'new',  -- 'new' | 'learning' | 'known'
    interval_days     integer not null default 1,
    ease              numeric not null default 1.7,
    next_review_date  date not null default current_date,
    last_reviewed_at  timestamptz,
    created_at        timestamptz not null default now(),
    unique (user_id, word_id)
);

create index if not exists idx_user_words_due on user_words (user_id, next_review_date);

alter table users add column if not exists daily_new_word_limit integer not null default 5;
