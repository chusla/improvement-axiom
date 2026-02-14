-- Supabase schema for the Improvement Axiom framework
-- Run this in the Supabase SQL editor to create the required tables.

-- Trajectories: user-level aggregate data
CREATE TABLE IF NOT EXISTS trajectories (
    user_id TEXT PRIMARY KEY,
    creation_rate REAL DEFAULT 0.0,
    propagation_rate REAL DEFAULT 0.0,
    compounding_direction REAL DEFAULT 0.0,
    current_direction REAL DEFAULT 0.0,
    current_magnitude REAL DEFAULT 0.0,
    current_confidence REAL DEFAULT 0.0,
    experience_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Experiences: individual recorded experiences
CREATE TABLE IF NOT EXISTS experiences (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES trajectories(user_id),
    description TEXT DEFAULT '',
    context TEXT DEFAULT '',
    user_rating REAL DEFAULT 0.5,
    provisional_intention TEXT DEFAULT 'pending',
    intention_confidence REAL DEFAULT 0.0,
    resonance_score REAL DEFAULT 0.0,
    quality_score REAL DEFAULT 0.0,
    quality_dimensions JSONB DEFAULT '{}',
    propagated BOOLEAN DEFAULT FALSE,
    propagation_events JSONB DEFAULT '[]',
    matrix_position TEXT DEFAULT 'Pending',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_experiences_user_id ON experiences(user_id);
CREATE INDEX IF NOT EXISTS idx_experiences_created_at ON experiences(created_at);

-- Follow-ups: post-experience observations
CREATE TABLE IF NOT EXISTS follow_ups (
    id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL REFERENCES experiences(id),
    user_id TEXT NOT NULL REFERENCES trajectories(user_id),
    source TEXT DEFAULT 'user_response',
    content TEXT DEFAULT '',
    created_something BOOLEAN DEFAULT FALSE,
    creation_description TEXT DEFAULT '',
    creation_magnitude REAL DEFAULT 0.0,
    shared_or_taught BOOLEAN DEFAULT FALSE,
    inspired_further_action BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_follow_ups_experience_id ON follow_ups(experience_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_user_id ON follow_ups(user_id);

-- Vector snapshots: point-in-time trajectory measurements (append-only)
-- experience_id is NULL for trajectory-level snapshots
CREATE TABLE IF NOT EXISTS vector_snapshots (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES trajectories(user_id),
    experience_id TEXT REFERENCES experiences(id),
    direction REAL DEFAULT 0.0,
    magnitude REAL DEFAULT 0.0,
    confidence REAL DEFAULT 0.0,
    horizon TEXT DEFAULT 'immediate',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vector_snapshots_user_id ON vector_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_vector_snapshots_experience_id ON vector_snapshots(experience_id);
CREATE INDEX IF NOT EXISTS idx_vector_snapshots_created_at ON vector_snapshots(created_at);

-- Conversation logs: raw chat messages for observability & review
CREATE TABLE IF NOT EXISTS conversation_logs (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    mode TEXT DEFAULT 'direct',               -- 'agent' or 'direct'
    metrics JSONB,                             -- framework metrics snapshot at this turn
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_logs_session ON conversation_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_conversation_logs_user ON conversation_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_logs_created_at ON conversation_logs(created_at);

-- Row Level Security (enable for production)
-- ALTER TABLE trajectories ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE experiences ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE follow_ups ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE vector_snapshots ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE conversation_logs ENABLE ROW LEVEL SECURITY;
