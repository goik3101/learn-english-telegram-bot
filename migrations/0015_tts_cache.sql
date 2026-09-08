-- M16: TTS 캐싱 (섹션16 AI/외부 API 호출 최소화 원칙 — 같은 텍스트는 재합성하지 않고 캐시 재사용)
create table if not exists tts_cache (
    id          bigserial primary key,
    cache_key   text not null unique,  -- sha256(language_code:voice_name:text)
    audio_data  bytea not null,        -- OGG_OPUS 인코딩 (텔레그램 sendVoice와 바로 호환)
    created_at  timestamptz not null default now()
);
