-- Twitter Agent schema for the Improvement Axiom framework
-- Run this in the Supabase SQL editor AFTER the base schema (supabase_schema.sql).

-- Ingested tweets: raw tweets captured from X/Twitter
CREATE TABLE IF NOT EXISTS ingested_tweets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tweet_url TEXT NOT NULL,
    author_handle TEXT,
    author_name TEXT,
    tweet_text TEXT NOT NULL,
    context_thread JSONB DEFAULT '[]',
    media_urls JSONB DEFAULT '[]',
    embedded_urls JSONB DEFAULT '[]',
    fetched_content JSONB DEFAULT '{}',
    response_mode TEXT DEFAULT 'short' CHECK (response_mode IN ('short', 'long')),
    ingested_at TIMESTAMPTZ DEFAULT now(),
    processed BOOLEAN DEFAULT FALSE,
    source TEXT DEFAULT 'extension'
);

CREATE INDEX IF NOT EXISTS idx_ingested_tweets_processed ON ingested_tweets(processed);
CREATE INDEX IF NOT EXISTS idx_ingested_tweets_ingested_at ON ingested_tweets(ingested_at);

-- Axiom evaluations: framework analysis of each tweet
CREATE TABLE IF NOT EXISTS axiom_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tweet_id UUID NOT NULL REFERENCES ingested_tweets(id) ON DELETE CASCADE,
    quality_score REAL,
    intention TEXT,
    quadrant TEXT,
    resonance_potential REAL,
    evaluation_reasoning TEXT,
    raw_llm_response JSONB,
    model_used TEXT DEFAULT 'claude-sonnet-4-5',
    evaluated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_axiom_evaluations_tweet_id ON axiom_evaluations(tweet_id);

-- Draft responses: AI-generated replies for review
CREATE TABLE IF NOT EXISTS draft_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tweet_id UUID NOT NULL REFERENCES ingested_tweets(id) ON DELETE CASCADE,
    evaluation_id UUID REFERENCES axiom_evaluations(id) ON DELETE SET NULL,
    draft_text TEXT NOT NULL,
    tone TEXT,
    axiom_aligned BOOLEAN DEFAULT TRUE,
    response_mode TEXT DEFAULT 'short' CHECK (response_mode IN ('short', 'long')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'posted', 'rejected', 'edited')),
    edited_text TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    posted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_draft_responses_tweet_id ON draft_responses(tweet_id);
CREATE INDEX IF NOT EXISTS idx_draft_responses_status ON draft_responses(status);

-- Agent config: store per-user settings (extension key, persona, etc.)
CREATE TABLE IF NOT EXISTS agent_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Seed default config
INSERT INTO agent_config (key, value) VALUES
    ('persona', '"default"'),
    ('auto_evaluate', 'true'),
    ('model', '"claude-sonnet-4-5"'),
    ('max_response_length', '280')
ON CONFLICT (key) DO NOTHING;

-- Enable realtime for the draft_responses table (for live dashboard updates)
-- ALTER PUBLICATION supabase_realtime ADD TABLE draft_responses;
