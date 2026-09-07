-- M11: 개인 텍스트 붙여넣기 학습 기록
-- 섹션3-2 "원문 텍스트는 전체 저장하지 않고 핵심만 추출 저장" 원칙에 따라 전문은 저장하지 않고
-- 앞부분 일부(source_excerpt)와 글자수만 남긴다.
create table if not exists custom_texts (
    id                     bigserial primary key,
    user_id                bigint not null references users (id) on delete cascade,
    level                  text not null,
    source_excerpt         text,
    source_char_count      integer not null,
    extracted_word_count   integer not null default 0,
    user_translation       text,
    ai_feedback            text,
    created_at             timestamptz not null default now()
);

create index if not exists idx_custom_texts_user on custom_texts (user_id);
