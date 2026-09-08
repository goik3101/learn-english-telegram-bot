-- M15: CHILD_BEGINNER 모드 (10세 이하, Stage0~5 — Stage6 듣기말하기는 TTS(M16) 이후로 보류)
-- 현재 학습 중인 단계. Stage0 알파벳부터 시작, 완료할 때마다 1씩 증가.
alter table users add column if not exists child_stage integer not null default 0;

-- Stage0(알파벳)/Stage1(파닉스)는 26자/한정된 파닉스 규칙이라 고정 커리큘럼으로 코드에 정적 데이터로 둔다(AI 생성 불필요).
-- Stage2(기초단어)~Stage5(짧은지문)는 AI로 생성해 재사용하는 콘텐츠뱅크.
create table if not exists child_beginner_content (
    id             bigserial primary key,
    stage          integer not null,       -- 2:기초단어 3:기초문장 4:QA 5:짧은지문
    passage_text   text,                    -- stage5 전용 지문 (그 외 stage는 null)
    prompt         text not null,           -- stage2:단어 / stage3:문장 / stage4:질문 / stage5:이해도 질문
    meaning_ko     text not null,           -- 정답 관련 한국어 뜻/설명
    choices        jsonb not null,          -- 4지선다
    correct_index  integer not null,
    created_at     timestamptz not null default now()
);

create index if not exists idx_child_beginner_content_stage on child_beginner_content (stage);

-- Stage를 처음 완료한 시점만 기록(재학습은 몇 번이든 가능하되 진도는 한 번만 전진).
create table if not exists child_beginner_progress (
    id            bigserial primary key,
    user_id       bigint not null references users (id) on delete cascade,
    stage         integer not null,
    completed_at  timestamptz not null default now(),
    unique (user_id, stage)
);
