-- M6 후속: 문법 개념 설명(사용자 피드백 반영) — 문제 풀기 전에 보여줄 짧은 개념 설명
alter table grammar_questions add column if not exists concept_intro text;
