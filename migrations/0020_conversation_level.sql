-- 개인 맞춤 난이도 시스템 4/4: 회화 — 전체 레벨(placement_level)과 독립적인 CEFR형 축.
-- 0(A1)~5(C2), 세션 종료 후 "쉬웠어요/적당해요/어려웠어요" 피드백으로만 오르내린다.
alter table users add column if not exists conversation_level integer not null default 2;
