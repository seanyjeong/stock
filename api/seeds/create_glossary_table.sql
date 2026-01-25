-- Daily Stock Story - 주식 용어 사전 테이블
-- pgvector 확장 필요 (vector 타입 사용)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS glossary_terms (
    id SERIAL PRIMARY KEY,
    term VARCHAR(100) NOT NULL,
    term_en VARCHAR(100),
    category VARCHAR(50) NOT NULL,
    definition TEXT NOT NULL,
    example TEXT,
    related_terms TEXT[],
    is_slang BOOLEAN DEFAULT FALSE,
    difficulty VARCHAR(20) DEFAULT 'beginner',
    embedding vector(768),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_glossary_embedding ON glossary_terms
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_glossary_term ON glossary_terms(term);
CREATE INDEX IF NOT EXISTS idx_glossary_category ON glossary_terms(category);
CREATE INDEX IF NOT EXISTS idx_glossary_is_slang ON glossary_terms(is_slang);
CREATE INDEX IF NOT EXISTS idx_glossary_difficulty ON glossary_terms(difficulty);

-- 유니크 제약조건 (term + category 조합)
CREATE UNIQUE INDEX IF NOT EXISTS idx_glossary_term_category ON glossary_terms(term, category);

COMMENT ON TABLE glossary_terms IS '주식 용어 사전 - 벡터 검색 지원';
COMMENT ON COLUMN glossary_terms.term IS '한글 용어명';
COMMENT ON COLUMN glossary_terms.term_en IS '영문 용어명';
COMMENT ON COLUMN glossary_terms.category IS '카테고리 (basic, technical, fundamental, short_squeeze, options, us_market, slang)';
COMMENT ON COLUMN glossary_terms.definition IS '용어 설명';
COMMENT ON COLUMN glossary_terms.example IS '사용 예시';
COMMENT ON COLUMN glossary_terms.related_terms IS '관련 용어 배열';
COMMENT ON COLUMN glossary_terms.is_slang IS '은어/속어 여부';
COMMENT ON COLUMN glossary_terms.difficulty IS '난이도 (beginner, intermediate, advanced)';
COMMENT ON COLUMN glossary_terms.embedding IS '텍스트 임베딩 벡터 (768차원)';
