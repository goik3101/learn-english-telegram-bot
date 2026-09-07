-- M7: 오늘의 학습(Planner) 세션 기록
create table if not exists learning_sessions (
    id                 bigserial primary key,
    user_id            bigint not null references users (id) on delete cascade,
    session_date       date not null default current_date,
    stages_completed   jsonb not null default '[]'::jsonb,  -- 예: ["vocab", "grammar"]
    ai_call_count      integer not null default 0,           -- M17 AI 사용량 조회에서 활용 예정
    started_at         timestamptz not null default now(),
    completed_at       timestamptz,
    unique (user_id, session_date)
);

create index if not exists idx_learning_sessions_user_date on learning_sessions (user_id, session_date);
