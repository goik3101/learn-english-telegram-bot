-- 개인 맞춤 난이도 시스템 1/4: 단어 — 실제 사용빈도(frequency_rank) 기반 밴드 적응 조정
alter table words add column if not exists frequency_rank integer;
create index if not exists idx_words_frequency_rank on words (frequency_rank);

-- 사용자의 현재 단어 난이도 밴드(0부터 시작, 낮을수록 쉬움) — placement_level과는 별개로
-- 신규 단어 선정 시에만 쓰이는 세밀한 조정 축이다.
alter table users add column if not exists word_band integer not null default 0;

-- 신규 단어(첫 학습) 완료 시의 밴드/정오답 기록. 최근 N개 정답률로 밴드 승급/강등을 판단한다.
-- SRS 복습(이미 배운 단어)은 여기 포함하지 않는다 — "새 단어를 처음 만났을 때 이 난이도가
-- 적절한가"를 측정하는 신호이기 때문.
create table if not exists user_word_attempts (
    id            bigserial primary key,
    user_id       bigint not null references users (id) on delete cascade,
    word_id       bigint not null references words (id) on delete cascade,
    band          integer not null,
    is_correct    boolean not null,
    attempted_at  timestamptz not null default now()
);

create index if not exists idx_user_word_attempts_user_band on user_word_attempts (user_id, band, attempted_at desc);
