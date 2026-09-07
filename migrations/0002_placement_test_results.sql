-- M3: 레벨 진단(V0) 결과 저장
create table if not exists placement_test_results (
    id              bigserial primary key,
    user_id         bigint not null references users (id) on delete cascade,
    word_correct    integer not null,
    word_total      integer not null,
    grammar_correct integer not null,
    grammar_total   integer not null,
    level           text not null,
    created_at      timestamptz not null default now()
);

create index if not exists idx_placement_results_user_id on placement_test_results (user_id);
-- users.placement_level 컬럼은 0001에서 이미 생성됨
