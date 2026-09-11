-- 문법 커리큘럼 재구성: 정적 18-topic 전역 리스트(app/grammar/curriculum.py, 이제 삭제됨)와
-- users.grammar_topic_index 방식을 폐기하고, CEFR(A1~C2) 기반 토픽 + 더 작은 파트(part) 단위
-- 진행으로 교체한다.
--
-- 버그리포트: 토픽 하나가 너무 크고, 신규 세트가 하루 5문제로 제한된 상태에서 숙달 판정이
-- "최근 10문제 중 80%"를 요구해 최소 2일 이상 걸렸다(사실상 "5문제만 나가고 멈춘 것처럼" 느껴짐).
-- 파트 단위로 잘게 쪼개고 숙달 기준을 "최소 5문제 시도 + 최근 5문제 80%"로 낮춰, 하루 세션
-- 하나로도 파트 하나를 끝낼 수 있게 한다.

create table if not exists grammar_topics (
    id            bigserial primary key,
    cefr_level    text not null,
    order_index   integer not null unique,
    name          text not null,
    description   text,
    is_exam_focus boolean not null default false,
    created_at    timestamptz not null default now()
);

create table if not exists grammar_parts (
    id                  bigserial primary key,
    topic_id            bigint not null references grammar_topics (id) on delete cascade,
    order_index         integer not null,
    global_order_index  integer not null unique,
    name                text not null,
    description         text,
    target_question_count integer not null default 8,
    created_at          timestamptz not null default now(),
    unique (topic_id, order_index)
);

create index if not exists idx_grammar_parts_topic on grammar_parts (topic_id);

-- grammar_questions은 이제 topic(문자열) 매칭이 아니라 part_id로 연결된다. topic/level 컬럼은
-- 하위호환/표시용으로 그대로 둔다(topic에는 grammar_topics.name을, level에는 CEFR_TO_LEGACY_LEVEL
-- 매핑값을 채운다).
alter table grammar_questions add column if not exists part_id bigint references grammar_parts (id) on delete set null;
alter table grammar_questions add column if not exists error_type text;
create index if not exists idx_grammar_questions_part on grammar_questions (part_id);

-- 사용자별 현재 진행 위치(토픽/파트 둘 다 명시적으로 저장).
create table if not exists user_grammar_progress (
    user_id          bigint primary key references users (id) on delete cascade,
    current_topic_id bigint references grammar_topics (id),
    current_part_id  bigint references grammar_parts (id),
    updated_at       timestamptz not null default now()
);

-- 사용자별 파트별 숙달 상태. 행이 없으면 아직 시도한 적 없는(잠긴) 파트로 취급한다.
create table if not exists user_grammar_part_progress (
    user_id       bigint not null references users (id) on delete cascade,
    part_id       bigint not null references grammar_parts (id) on delete cascade,
    status        text not null default 'in_progress',  -- in_progress | mastered
    attempt_count integer not null default 0,
    correct_count integer not null default 0,
    updated_at    timestamptz not null default now(),
    primary key (user_id, part_id)
);

-- 기존 전역 순차 인덱스는 새 progress 테이블로 대체되어 더 이상 쓰이지 않는다.
alter table users drop column if exists grammar_topic_index;
