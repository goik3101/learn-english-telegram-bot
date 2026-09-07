-- M9: 회화(Conversation) 세션 + 메시지 기록
create table if not exists conversation_sessions (
    id            bigserial primary key,
    user_id       bigint not null references users (id) on delete cascade,
    level         text not null,
    turn_count    integer not null default 0,
    started_at    timestamptz not null default now(),
    completed_at  timestamptz
);

create table if not exists conversation_messages (
    id            bigserial primary key,
    session_id    bigint not null references conversation_sessions (id) on delete cascade,
    role          text not null,  -- 'user' | 'model'
    content       text not null,
    created_at    timestamptz not null default now()
);

create index if not exists idx_conversation_sessions_user on conversation_sessions (user_id);
create index if not exists idx_conversation_messages_session on conversation_messages (session_id);
