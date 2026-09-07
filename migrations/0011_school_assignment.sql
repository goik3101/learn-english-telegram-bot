-- M12: 학교 수행평가(단일 글) 텍스트 학습 기록
-- M11(custom_texts)과 동일하게 원문 전체는 저장하지 않고 앞부분 일부(source_excerpt)와 글자수만 남긴다.
create table if not exists school_assignments (
    id                     bigserial primary key,
    user_id                bigint not null references users (id) on delete cascade,
    level                  text not null,
    source_excerpt         text,
    source_char_count      integer not null,
    extracted_word_count   integer not null default 0,
    grammar_explanation    text,
    exam_question_count    integer not null default 0,
    exam_correct_count     integer not null default 0,
    created_at             timestamptz not null default now()
);

create index if not exists idx_school_assignments_user on school_assignments (user_id);
