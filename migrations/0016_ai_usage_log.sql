-- M17: AI/외부 API 사용량 모니터링
-- 사용자별이 아니라 프로젝트 전체 호출량을 추적한다 — Gemini/Google Cloud TTS 무료 티어 한도가
-- 사용자별이 아니라 프로젝트(API 키) 단위로 걸리기 때문(M9에서 실측 확인한 사실과 동일한 전제).
create table if not exists ai_usage_log (
    id          bigserial primary key,
    provider    text not null,   -- 'gemini' | 'google_tts'
    called_at   timestamptz not null default now()
);

create index if not exists idx_ai_usage_log_called_at on ai_usage_log (called_at);
create index if not exists idx_ai_usage_log_provider on ai_usage_log (provider);
