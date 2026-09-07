-- M0~M2: users 기본 구조 + 승인 체계 + 나이/학습모드
create table if not exists users (
    id                bigserial primary key,
    telegram_id       text unique not null,
    approved          boolean not null default false,
    role              text not null default 'user',      -- 'admin' | 'user'
    age               integer,
    learning_mode     text,                                -- 'GENERAL' | 'CHILD_BRIDGE' | 'CHILD_BEGINNER'
    native_language   text not null default 'ko',
    placement_level   text,
    target_use_case   text,
    created_at        timestamptz not null default now(),
    last_active_at    timestamptz not null default now()
);

create index if not exists idx_users_telegram_id on users (telegram_id);
create index if not exists idx_users_approved on users (approved);
