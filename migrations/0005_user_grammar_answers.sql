-- M6: 문법 학습 오답 기록
create table if not exists user_grammar_answers (
    id            bigserial primary key,
    user_id       bigint not null references users (id) on delete cascade,
    question_id   bigint not null references grammar_questions (id) on delete cascade,
    is_correct    boolean not null,
    error_tag     text,       -- 오답 시 grammar_questions.topic을 그대로 기록 (섹션18 [결정필요]: 별도 태그 체계 대신 재사용)
    is_review     boolean not null default false,  -- true = /복습(무제한 반복), false = 하루 1회 신규 세트
    answered_at   timestamptz not null default now()
);

create index if not exists idx_user_grammar_answers_user on user_grammar_answers (user_id);
create index if not exists idx_user_grammar_answers_user_date on user_grammar_answers (user_id, answered_at);
