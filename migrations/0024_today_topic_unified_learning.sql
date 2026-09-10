-- 오늘의 주제 기반 통합 학습: 단어/해석/회화가 서로 무관하게 각자 콘텐츠를 뽑다 보니 해석 지문이
-- 사용자 수준과 동떨어진 학술 어휘로 생성되는 문제(사용자 피드백)를 해결하기 위해, 하루 단위로
-- "오늘의 주제"와 그 주제의 핵심 단어 풀을 하나 정해서 세 영역이 공유하게 한다.
alter table learning_sessions add column if not exists today_topic text;
alter table learning_sessions add column if not exists today_topic_word_ids bigint[] not null default '{}';
alter table learning_sessions add column if not exists today_reading_passage_id bigint references reading_passages (id);

-- M19(회화 사전 단어학습)에서 회화 전용으로 만들었던 conversation_topic_words를 범용 명칭으로 바꾼다 —
-- 이제 단어학습/해석/회화가 전부 이 테이블을 공유한다("오늘의 주제 단어"와 "회화 사전학습 단어"를
-- 하나로 통합, 두 번 따로 만들지 않음).
alter table conversation_topic_words rename to topic_words;

-- 회화가 더 이상 독립적으로 자기 주제를 순환시키지 않고(learning_sessions.today_topic을 공유) —
-- 이 컬럼은 더 이상 쓰이지 않아 제거한다.
alter table users drop column if exists conversation_topic_index;
