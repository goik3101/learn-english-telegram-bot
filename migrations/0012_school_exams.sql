-- M13: 학교 시험 관리 확장 (시험/단원/자료/선생님강조/D-Day/시험직전복습)
create table if not exists school_exams (
    id             bigserial primary key,
    user_id        bigint not null references users (id) on delete cascade,
    subject        text not null,
    exam_date      date not null,
    unit_info      text,
    teacher_notes  text,
    created_at     timestamptz not null default now()
);

create index if not exists idx_school_exams_user on school_exams (user_id);

-- 학교 수행평가 자료(M12)를 특정 시험에 연결(자료)하고, 생성된 예상문제별 정오답을 남겨
-- 시험직전복습에서 오답만 다시 추릴 수 있게 한다.
alter table school_assignments add column if not exists exam_id bigint references school_exams (id) on delete set null;
alter table school_assignments add column if not exists question_details jsonb;

create index if not exists idx_school_assignments_exam on school_assignments (exam_id);

-- 시험직전복습 이력(진행 여부/점수 기록용, 원본 오답 기록은 수정하지 않음)
create table if not exists school_exam_reviews (
    id              bigserial primary key,
    exam_id         bigint not null references school_exams (id) on delete cascade,
    user_id         bigint not null references users (id) on delete cascade,
    question_count  integer not null default 0,
    correct_count   integer not null default 0,
    reviewed_at     timestamptz not null default now()
);

create index if not exists idx_school_exam_reviews_exam on school_exam_reviews (exam_id);
