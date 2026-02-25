-- ============================================================================
-- OpenClaw Memory Module Schema
-- Extends OpenClaw Knowledgebase with multi-agent shared memory
--
-- REQUIRES: schema.sql applied first (kb_sources, kb_chunks)
-- REQUIRES: pgcrypto extension for API key hashing
-- ============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- CUSTOM TYPES
-- ============================================================================

DO $$ BEGIN
    CREATE TYPE mb_memory_type AS ENUM ('episodic', 'semantic', 'procedural');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE mb_scope AS ENUM ('private', 'team', 'global');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- ROLES for legacy compatibility
-- Instead of fragile "NOT EXISTS" checks, we use a dedicated role.
-- Legacy clients authenticate with this role and bypass agent-based RLS.
-- ============================================================================

DO $$ BEGIN
    CREATE ROLE mb_legacy_role NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Grant legacy role full access to existing kb tables
GRANT SELECT, INSERT, UPDATE, DELETE ON kb_sources TO mb_legacy_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON kb_chunks TO mb_legacy_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mb_legacy_role;

-- ============================================================================
-- TABLE: mb_agents — Agent Registry
-- ============================================================================

CREATE TABLE IF NOT EXISTS mb_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    agent_type TEXT NOT NULL DEFAULT 'openclaw',  -- openclaw, human, service
    api_key_hash TEXT NOT NULL,                   -- bcrypt via pgcrypto
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS mb_agents_name_idx ON mb_agents(name);

-- ============================================================================
-- TABLE: mb_teams — Agent groups
-- ============================================================================

CREATE TABLE IF NOT EXISTS mb_teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_by UUID REFERENCES mb_agents(id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mb_team_members (
    team_id UUID REFERENCES mb_teams(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES mb_agents(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',  -- admin, member, readonly
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (team_id, agent_id)
);

CREATE INDEX IF NOT EXISTS mb_team_members_agent_idx ON mb_team_members(agent_id);

-- ============================================================================
-- TABLE: mb_memory — Unified memory entries
--
-- NOTE on embedding dimensions: Currently 768 for nomic-embed-text.
-- Changing models requires rebuilding this table's vector column and index.
-- See EMBEDDING_DIMENSIONS in config. Document this dependency.
-- ============================================================================

CREATE TABLE IF NOT EXISTS mb_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES mb_agents(id) ON DELETE CASCADE,

    -- Memory classification
    memory_type mb_memory_type NOT NULL DEFAULT 'semantic',
    scope mb_scope NOT NULL DEFAULT 'private',

    -- Content
    content TEXT NOT NULL,
    summary TEXT,
    embedding vector(768),

    -- Optional link to existing RAG
    source_id INTEGER REFERENCES kb_sources(id) ON DELETE SET NULL,
    chunk_id INTEGER REFERENCES kb_chunks(id) ON DELETE SET NULL,

    -- Organization
    tags TEXT[] DEFAULT '{}',
    namespace TEXT NOT NULL DEFAULT 'default',
    metadata JSONB DEFAULT '{}',

    -- Lifecycle — importance for decay/prioritization
    -- NOTE: access_count is NOT updated inline (see mb_memory_access_log)
    importance FLOAT DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
    access_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ               -- NULL = never expires
);

-- HNSW index: better recall & speed under concurrency than ivfflat,
-- no need to rebuild as table grows.
CREATE INDEX IF NOT EXISTS mb_memory_embedding_idx ON mb_memory
    USING hnsw (embedding vector_cosine_ops);

-- Filtered query indexes
CREATE INDEX IF NOT EXISTS mb_memory_agent_idx ON mb_memory(agent_id);
CREATE INDEX IF NOT EXISTS mb_memory_scope_idx ON mb_memory(scope);
CREATE INDEX IF NOT EXISTS mb_memory_type_idx ON mb_memory(memory_type);
CREATE INDEX IF NOT EXISTS mb_memory_namespace_idx ON mb_memory(namespace);
CREATE INDEX IF NOT EXISTS mb_memory_tags_idx ON mb_memory USING gin(tags);
CREATE INDEX IF NOT EXISTS mb_memory_content_fts_idx ON mb_memory
    USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS mb_memory_expires_idx ON mb_memory(expires_at)
    WHERE expires_at IS NOT NULL;

-- ============================================================================
-- TABLE: mb_memory_access_log — Append-only access log
--
-- Solves row-lock contention: instead of UPDATE mb_memory SET access_count++
-- on every read (which locks the row under concurrent multi-agent reads),
-- we append to this log table (no locks on mb_memory) and aggregate via
-- a periodic cron job.
-- ============================================================================

CREATE TABLE IF NOT EXISTS mb_memory_access_log (
    id BIGSERIAL PRIMARY KEY,
    memory_id UUID NOT NULL REFERENCES mb_memory(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES mb_agents(id) ON DELETE CASCADE,
    accessed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS mb_access_log_memory_idx ON mb_memory_access_log(memory_id);
CREATE INDEX IF NOT EXISTS mb_access_log_time_idx ON mb_memory_access_log(accessed_at);

-- ============================================================================
-- TABLE: mb_kb_access — Share existing RAG sources with agents/teams
-- ============================================================================

CREATE TABLE IF NOT EXISTS mb_kb_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id INTEGER NOT NULL REFERENCES kb_sources(id) ON DELETE CASCADE,

    -- Grantee: agent, team, or global (both NULL)
    agent_id UUID REFERENCES mb_agents(id) ON DELETE CASCADE,
    team_id UUID REFERENCES mb_teams(id) ON DELETE CASCADE,
    scope mb_scope NOT NULL DEFAULT 'global',

    permission TEXT NOT NULL DEFAULT 'read',  -- read, write, admin
    granted_by UUID REFERENCES mb_agents(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT mb_kb_access_single_grantee CHECK (
        (agent_id IS NOT NULL AND team_id IS NULL) OR
        (agent_id IS NULL AND team_id IS NOT NULL) OR
        (agent_id IS NULL AND team_id IS NULL AND scope = 'global')
    ),
    -- Prevent duplicate grants
    UNIQUE(source_id, agent_id, team_id)
);

CREATE INDEX IF NOT EXISTS mb_kb_access_source_idx ON mb_kb_access(source_id);
CREATE INDEX IF NOT EXISTS mb_kb_access_agent_idx ON mb_kb_access(agent_id);
CREATE INDEX IF NOT EXISTS mb_kb_access_team_idx ON mb_kb_access(team_id);

-- ============================================================================
-- ROW-LEVEL SECURITY
-- ============================================================================

ALTER TABLE mb_memory ENABLE ROW LEVEL SECURITY;

-- Legacy role bypasses RLS entirely (stable, not data-dependent)
CREATE POLICY mb_memory_legacy ON mb_memory
    FOR ALL TO mb_legacy_role
    USING (true) WITH CHECK (true);

-- Agent sees own private memories
CREATE POLICY mb_memory_own ON mb_memory
    FOR ALL USING (
        agent_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'agent_id')::uuid
    )
    WITH CHECK (
        agent_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'agent_id')::uuid
    );

-- All agents can read global memories
CREATE POLICY mb_memory_global_read ON mb_memory
    FOR SELECT USING (scope = 'global');

-- Team members can read team memories
CREATE POLICY mb_memory_team_read ON mb_memory
    FOR SELECT USING (
        scope = 'team'
        AND EXISTS (
            SELECT 1
            FROM mb_team_members my_teams
            JOIN mb_team_members their_teams ON my_teams.team_id = their_teams.team_id
            WHERE my_teams.agent_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'agent_id')::uuid
              AND their_teams.agent_id = mb_memory.agent_id
        )
    );

-- RLS on kb_chunks for multi-agent RAG access
ALTER TABLE kb_chunks ENABLE ROW LEVEL SECURITY;

-- Legacy role gets full access (no fragile NOT EXISTS check)
CREATE POLICY kb_chunks_legacy ON kb_chunks
    FOR ALL TO mb_legacy_role
    USING (true) WITH CHECK (true);

-- Agent access via mb_kb_access grants
CREATE POLICY kb_chunks_agent_access ON kb_chunks
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM mb_kb_access ka
            LEFT JOIN mb_team_members tm ON ka.team_id = tm.team_id
            WHERE ka.source_id = kb_chunks.source_id
              AND (
                  ka.scope = 'global'
                  OR ka.agent_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'agent_id')::uuid
                  OR tm.agent_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'agent_id')::uuid
              )
        )
    );

-- ============================================================================
-- RPC FUNCTIONS
-- All use SET search_path = public to prevent schema injection attacks.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Agent authentication: validates API key, returns agent info
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_authenticate_agent(p_api_key TEXT)
RETURNS TABLE (agent_id UUID, agent_name TEXT, agent_type TEXT)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT a.id, a.name, a.agent_type
    FROM mb_agents a
    WHERE a.api_key_hash = crypt(p_api_key, a.api_key_hash)
      AND a.is_active = TRUE;

    -- Update last_seen asynchronously-safe (single row, minimal lock)
    UPDATE mb_agents
    SET last_seen_at = NOW()
    WHERE api_key_hash = crypt(p_api_key, api_key_hash)
      AND is_active = TRUE;
END;
$$;

-- ----------------------------------------------------------------------------
-- Register a new agent
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_register_agent(
    p_name TEXT,
    p_api_key TEXT,
    p_display_name TEXT DEFAULT NULL,
    p_agent_type TEXT DEFAULT 'openclaw',
    p_metadata JSONB DEFAULT '{}'
)
RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    new_id UUID;
BEGIN
    INSERT INTO mb_agents (name, display_name, agent_type, api_key_hash, metadata)
    VALUES (p_name, p_display_name, p_agent_type, crypt(p_api_key, gen_salt('bf')), p_metadata)
    RETURNING id INTO new_id;
    RETURN new_id;
END;
$$;

-- ----------------------------------------------------------------------------
-- Search agent memory only (with proper vector index usage)
--
-- KEY FIX: Each subquery uses ORDER BY embedding <=> vector LIMIT N
-- to ensure pgvector's HNSW/ivfflat index is used for ANN search
-- BEFORE relational filters are applied. Then we combine and re-sort.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_search_memory(
    p_agent_id UUID,
    p_query_embedding vector(768),
    p_match_count INT DEFAULT 10,
    p_similarity_threshold FLOAT DEFAULT 0.5,
    p_memory_types mb_memory_type[] DEFAULT NULL,
    p_scopes mb_scope[] DEFAULT ARRAY['private', 'team', 'global']::mb_scope[],
    p_namespace TEXT DEFAULT NULL,
    p_tags TEXT[] DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    agent_id UUID,
    agent_name TEXT,
    memory_type mb_memory_type,
    scope mb_scope,
    content TEXT,
    summary TEXT,
    tags TEXT[],
    namespace TEXT,
    metadata JSONB,
    importance FLOAT,
    similarity FLOAT,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    WITH candidates AS (
        -- Use ORDER BY <=> LIMIT to leverage HNSW index for ANN
        SELECT
            m.id, m.agent_id, m.memory_type, m.scope,
            m.content, m.summary, m.tags, m.namespace,
            m.metadata, m.importance, m.created_at,
            m.embedding,
            1 - (m.embedding <=> p_query_embedding) AS sim
        FROM mb_memory m
        WHERE m.embedding IS NOT NULL
          AND (m.expires_at IS NULL OR m.expires_at > NOW())
        ORDER BY m.embedding <=> p_query_embedding
        LIMIT p_match_count * 5  -- over-fetch for post-filtering
    )
    SELECT
        c.id, c.agent_id, a.name AS agent_name,
        c.memory_type, c.scope,
        c.content, c.summary, c.tags, c.namespace,
        c.metadata, c.importance,
        c.sim AS similarity,
        c.created_at
    FROM candidates c
    JOIN mb_agents a ON c.agent_id = a.id
    WHERE c.sim > p_similarity_threshold
      -- Scope/permission filtering (AFTER ANN search)
      AND (
          (c.scope = 'private' AND c.agent_id = p_agent_id)
          OR (c.scope = 'global')
          OR (c.scope = 'team' AND EXISTS (
              SELECT 1 FROM mb_team_members t1
              JOIN mb_team_members t2 ON t1.team_id = t2.team_id
              WHERE t1.agent_id = p_agent_id AND t2.agent_id = c.agent_id
          ))
      )
      AND (c.scope = ANY(p_scopes))
      AND (p_memory_types IS NULL OR c.memory_type = ANY(p_memory_types))
      AND (p_namespace IS NULL OR c.namespace = p_namespace)
      AND (p_tags IS NULL OR c.tags && p_tags)
    ORDER BY c.sim DESC
    LIMIT p_match_count;
END;
$$;

-- ----------------------------------------------------------------------------
-- Combined search: Memory + RAG chunks (unified retrieval)
--
-- Each source (memory, rag) does its own ANN search with LIMIT,
-- then results are merged and re-sorted. This ensures both HNSW indexes
-- are used independently.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_search_all(
    p_agent_id UUID,
    p_query_embedding vector(768),
    p_match_count INT DEFAULT 10,
    p_similarity_threshold FLOAT DEFAULT 0.5
)
RETURNS TABLE (
    result_type TEXT,
    result_id TEXT,
    agent_name TEXT,
    content TEXT,
    similarity FLOAT,
    metadata JSONB
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    WITH
    -- Step 1: ANN search on mb_memory (uses HNSW index)
    memory_ann AS (
        SELECT m.id, m.agent_id, m.scope, m.content,
               m.memory_type, m.tags,
               1 - (m.embedding <=> p_query_embedding) AS sim
        FROM mb_memory m
        WHERE m.embedding IS NOT NULL
          AND (m.expires_at IS NULL OR m.expires_at > NOW())
        ORDER BY m.embedding <=> p_query_embedding
        LIMIT p_match_count * 3
    ),
    -- Step 2: Filter memory by permissions
    memory_filtered AS (
        SELECT ma.id, ma.agent_id, ma.content, ma.sim,
               ma.memory_type, ma.tags
        FROM memory_ann ma
        WHERE ma.sim > p_similarity_threshold
          AND (
              (ma.scope = 'private' AND ma.agent_id = p_agent_id)
              OR (ma.scope = 'global')
              OR (ma.scope = 'team' AND EXISTS (
                  SELECT 1 FROM mb_team_members t1
                  JOIN mb_team_members t2 ON t1.team_id = t2.team_id
                  WHERE t1.agent_id = p_agent_id AND t2.agent_id = ma.agent_id
              ))
          )
    ),
    -- Step 3: ANN search on kb_chunks (uses existing vector index)
    rag_ann AS (
        SELECT c.id, c.source_id, c.content, c.url, c.title,
               1 - (c.embedding <=> p_query_embedding) AS sim
        FROM kb_chunks c
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> p_query_embedding
        LIMIT p_match_count * 3
    ),
    -- Step 4: Filter RAG by access permissions
    rag_filtered AS (
        SELECT ra.id, ra.content, ra.url, ra.title, ra.sim
        FROM rag_ann ra
        WHERE ra.sim > p_similarity_threshold
          AND EXISTS (
              SELECT 1 FROM mb_kb_access ka
              LEFT JOIN mb_team_members tm ON ka.team_id = tm.team_id
              WHERE ka.source_id = ra.source_id
                AND (
                    ka.scope = 'global'
                    OR ka.agent_id = p_agent_id
                    OR tm.agent_id = p_agent_id
                )
          )
    ),
    -- Step 5: Combine both sources
    combined AS (
        SELECT
            'memory'::TEXT AS result_type,
            mf.id::TEXT AS result_id,
            a.name AS agent_name,
            mf.content,
            mf.sim AS similarity,
            jsonb_build_object(
                'memory_type', mf.memory_type,
                'tags', mf.tags
            ) AS metadata
        FROM memory_filtered mf
        JOIN mb_agents a ON mf.agent_id = a.id

        UNION ALL

        SELECT
            'rag'::TEXT,
            rf.id::TEXT,
            NULL::TEXT,
            rf.content,
            rf.sim,
            jsonb_build_object('url', rf.url, 'title', rf.title)
        FROM rag_filtered rf
    )
    SELECT * FROM combined
    ORDER BY combined.similarity DESC
    LIMIT p_match_count;
END;
$$;

-- ----------------------------------------------------------------------------
-- Log memory access (append-only, no row locks on mb_memory)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_log_access(p_memory_id UUID, p_agent_id UUID)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO mb_memory_access_log (memory_id, agent_id)
    VALUES (p_memory_id, p_agent_id);
END;
$$;

-- ----------------------------------------------------------------------------
-- Aggregate access counts (run via pg_cron in off-peak hours)
-- Moves counts from access log into mb_memory.access_count in bulk.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_aggregate_access_counts()
RETURNS INTEGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    rows_processed INTEGER;
BEGIN
    WITH counts AS (
        SELECT memory_id, COUNT(*) AS cnt
        FROM mb_memory_access_log
        GROUP BY memory_id
    ),
    updated AS (
        UPDATE mb_memory m
        SET access_count = m.access_count + c.cnt,
            updated_at = NOW()
        FROM counts c
        WHERE m.id = c.memory_id
        RETURNING m.id
    )
    SELECT COUNT(*) INTO rows_processed FROM updated;

    -- Clear processed logs
    DELETE FROM mb_memory_access_log;

    RETURN rows_processed;
END;
$$;

-- Schedule with pg_cron (run manually if pg_cron not available):
-- SELECT cron.schedule('mb-access-counts', '0 3 * * *', 'SELECT mb_aggregate_access_counts()');

-- ----------------------------------------------------------------------------
-- Purge expired memories
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_purge_expired()
RETURNS INTEGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    rows_deleted INTEGER;
BEGIN
    DELETE FROM mb_memory
    WHERE expires_at IS NOT NULL AND expires_at < NOW();
    GET DIAGNOSTICS rows_deleted = ROW_COUNT;
    RETURN rows_deleted;
END;
$$;

-- ----------------------------------------------------------------------------
-- Bootstrap: grant an agent global access to all existing kb_sources
-- Useful during migration Phase 2.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_bootstrap_agent_access(p_agent_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    rows_granted INTEGER;
BEGIN
    INSERT INTO mb_kb_access (source_id, scope, granted_by)
    SELECT s.id, 'global', p_agent_id
    FROM kb_sources s
    WHERE NOT EXISTS (
        SELECT 1 FROM mb_kb_access ka
        WHERE ka.source_id = s.id AND ka.scope = 'global'
    );
    GET DIAGNOSTICS rows_granted = ROW_COUNT;
    RETURN rows_granted;
END;
$$;

-- ----------------------------------------------------------------------------
-- Stats for an agent
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mb_agent_stats(p_agent_id UUID)
RETURNS TABLE (
    own_memories BIGINT,
    accessible_memories BIGINT,
    accessible_rag_sources BIGINT,
    teams_count BIGINT
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT COUNT(*) FROM mb_memory WHERE agent_id = p_agent_id),
        (SELECT COUNT(*) FROM mb_memory
         WHERE agent_id = p_agent_id
            OR scope = 'global'
            OR (scope = 'team' AND EXISTS (
                SELECT 1 FROM mb_team_members t1
                JOIN mb_team_members t2 ON t1.team_id = t2.team_id
                WHERE t1.agent_id = p_agent_id AND t2.agent_id = mb_memory.agent_id
            ))
        ),
        (SELECT COUNT(DISTINCT ka.source_id) FROM mb_kb_access ka
         LEFT JOIN mb_team_members tm ON ka.team_id = tm.team_id
         WHERE ka.scope = 'global'
            OR ka.agent_id = p_agent_id
            OR tm.agent_id = p_agent_id
        ),
        (SELECT COUNT(*) FROM mb_team_members WHERE agent_id = p_agent_id);
END;
$$;
