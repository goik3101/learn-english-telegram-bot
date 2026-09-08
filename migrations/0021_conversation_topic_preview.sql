-- 회화 사전 단어학습: 오늘의 대화 주제 선정(순환 인덱스) + 주제별 핵심 단어 콘텐츠뱅크 캐싱 +
-- 세션에 어떤 주제/단어로 진행했는지 기록.
alter table users add column if not exists conversation_topic_index integer not null default 0;

alter table conversation_sessions add column if not exists topic text;
alter table conversation_sessions add column if not exists preview_word_ids bigint[] not null default '{}';

-- words(콘텐츠뱅크)와 별도 연결 테이블로 둔다 — 같은 단어가 주제 없이도 이미 존재할 수 있고(일반
-- 단어학습), 문법 key_vocabulary(M18)와 동일하게 words에는 그대로 합류시키되 주제 태그만 별도 관리.
create table if not exists conversation_topic_words (
    id             bigserial primary key,
    topic          text not null,
    level          text not null,
    learning_mode  text not null default 'GENERAL',
    word_id        bigint not null references words (id) on delete cascade,
    created_at     timestamptz not null default now(),
    unique (topic, level, learning_mode, word_id)
);

create index if not exists idx_conversation_topic_words_lookup on conversation_topic_words (topic, level, learning_mode);
