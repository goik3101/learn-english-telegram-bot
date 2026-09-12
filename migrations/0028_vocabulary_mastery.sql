-- V2 학습 엔진 1/4: 단어 암기(vocabulary memory) — "한 번 맞춤 = 암기 완료"로 처리하지 않기 위한
-- 학습단계(learning steps) 상태머신에 필요한 컬럼들. 전부 additive(add column if not exists)이므로
-- 기존 데이터/조회에 영향 없고, 재실행해도 안전하다.
--
-- mastery 값: 'new'(아직 학습 시작 전) | 'learning_step_1'(첫 정답, 같은 날/세션 내 재확인 대기) |
-- 'learning_step_2'(다음날 재확인까지 성공, 정규 SRS 간격 진입 준비) | 'review'(정규 SRS 복습
-- 사이클에 진입) | 'mastered'(consecutive_correct 충분 + 장기간격 성공 이력).
alter table user_words add column if not exists correct_count integer not null default 0;
alter table user_words add column if not exists wrong_count integer not null default 0;
alter table user_words add column if not exists hint_used_count integer not null default 0;
alter table user_words add column if not exists consecutive_correct integer not null default 0;
alter table user_words add column if not exists first_exposed_at timestamptz;
alter table user_words add column if not exists last_wrong_at timestamptz;
alter table user_words add column if not exists mastery text not null default 'new';

-- 기존 행(마이그레이션 이전에 이미 upsert_word_progress를 최소 한 번 거친 단어)을 신규 단어와
-- 똑같이 학습단계 처음부터 다시 시키면 퇴보다 — 정규 SRS 사이클(review)로 바로 배정한다.
--
-- 검증 중 실제 프로덕션 데이터로 확인한 중요한 함정: review_count는 migration 0022에서
-- `default 0`으로 나중에 추가된 컬럼이라, 0022 적용 이전에 이미 생성된 행은 review_count가
-- 0으로 남아있다(실측: 현재 60행 중 52행, 87%가 review_count=0). "review_count>=1"을 조건으로
-- 걸면 이 52행이 전부 걸러지지 않고 mastery='new'로 남아, 이미 충분히 학습된 단어가 다음 정답
-- 때 학습단계 처음부터(1일 간격) 다시 시작하는 심각한 퇴행이 생긴다 — 그래서 review_count
-- 조건 없이 무조건 승격시킨다.
-- 재실행 안전성: 애플리케이션 코드(app/vocab/mastery.py의 apply_answer)는 신규 단어의 첫
-- 응답에서도 절대 mastery='new'를 다시 쓰지 않는다(정답이면 learning_step_2, 오답이면
-- learning_step_1로 곧장 전이) — 즉 upsert_word_progress를 거친 행은 그 시점부터 다시는
-- mastery='new'가 되지 않는다. 따라서 이 UPDATE는 "이 마이그레이션 적용 시점에 이미 존재하던
-- 행"만 정확히 잡아내며, 이 마이그레이션을 몇 번을 다시 실행해도(또는 나중에 실행해도) 그 시점의
-- 진짜 신규 단어(아직 한 번도 응답한 적 없어 행 자체가 없는 단어)에는 전혀 영향을 주지 않는다.
update user_words set mastery = 'review' where mastery = 'new';
