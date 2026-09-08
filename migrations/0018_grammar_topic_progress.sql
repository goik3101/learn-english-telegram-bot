-- 개인 맞춤 난이도 시스템 2/4: 문법 — 레벨별 고정 커리큘럼(app/grammar/curriculum.py) 진행 위치.
-- 한 주제에서 최소 10문제 이상 풀고 정답률 80% 이상이 되어야 다음 주제(인덱스+1)로 진행한다.
alter table users add column if not exists grammar_topic_index integer not null default 0;
