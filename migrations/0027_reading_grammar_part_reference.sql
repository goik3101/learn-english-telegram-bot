-- 해석(Reading)을 문법 학습과 통합: 그날 생성된 지문이 어떤 grammar_part(+오늘의 주제 단어)를
-- 기반으로 만들어졌는지 참조를 남겨 재사용/디버깅을 가능하게 한다.
alter table reading_passages add column if not exists source_grammar_part_id bigint references grammar_parts (id);
