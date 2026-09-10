-- 단어 암기 효율 개선(사용자 피드백, 연구 근거): 이중부호화(dual coding) — 텍스트와 함께 이미지를
-- 보여주면 기억에 도움이 된다는 연구에 따라, 성인/CHILD_BRIDGE 모드 단어카드에도 이모지 1개를
-- 함께 보여준다(기존에는 CHILD_BEGINNER 전용이었음).
alter table words add column if not exists emoji text;
