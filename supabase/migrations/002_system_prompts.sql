-- System prompts table for Arete and Axiom evaluation prompts
-- Prompts are stored here and fetched at runtime by edge functions.
-- Source of truth: prompts/*.md files, synced via scripts/prompts-push.ts

CREATE TABLE IF NOT EXISTS system_prompts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT NOT NULL UNIQUE,
    prompt_text TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    version     TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_system_prompts_slug ON system_prompts(slug);
CREATE INDEX IF NOT EXISTS idx_system_prompts_active ON system_prompts(is_active);

ALTER TABLE system_prompts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON system_prompts
    FOR ALL TO service_role USING (true);
