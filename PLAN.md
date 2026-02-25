# OpenClaw Knowledgebase - Development Plan

## Status: v0.2.0

### Completed Features

#### 1. Core Infrastructure
- [x] Supabase client with configurable table prefix
- [x] Ollama embedding integration
- [x] Semantic search via RPC functions
- [x] Hybrid search (semantic + keyword)
- [x] Fallback client-side vector search
- [x] Stats and health endpoints

#### 2. Ingestion Pipeline
- [x] **Chunker** - Text splitting with overlap
  - Paragraph/sentence/word break points
  - Markdown-aware with header preservation
- [x] **Web Crawler** - URL ingestion
  - Single page or recursive
  - Configurable depth (0-3)
  - Rate limiting
  - Sitemap support
- [x] **Document Parser** - File processing
  - Native: TXT, MD, RST, JSON, YAML, CSV, TSV
  - Docling: PDF, DOCX, PPTX, XLSX, HTML

#### 3. CLI
- [x] `kb status` - Check connections
- [x] `kb find` - Search with options
- [x] `kb sources` - List sources
- [x] `kb embed` - Generate embeddings
- [x] `kb serve` - Start web UI

#### 4. Web UI
- [x] Dashboard with stats
- [x] Live search with HTMX
- [x] Sources list with delete
- [x] Add Source modal (crawl/upload)
- [x] Settings page
- [x] Glassmorphism design

#### 5. Multi-Agent Memory Module (v0.2.0)
- [x] Agent registration and API key auth (pgcrypto bcrypt)
- [x] Memory types: episodic, semantic, procedural
- [x] Scoped access: private, team, global
- [x] Teams with role-based membership
- [x] Unified search across memory + RAG (mb_search_all)
- [x] HNSW vector index (replaces ivfflat for memory)
- [x] Append-only access logging (no row-lock contention)
- [x] Row-Level Security with role-based legacy bypass
- [x] Bootstrap skill for agent self-configuration
- [x] Schema injection protection (SET search_path)

---

## TODO

### High Priority
- [ ] Security hardening (XSS fix, SSRF validation, CSRF tokens)
- [ ] Rate limiting on API endpoints
- [ ] Input validation (URL format, max_depth bounds, file size limits)

### Medium Priority
- [ ] Better error messages in UI (sanitize stack traces)
- [ ] Batch delete/operations
- [ ] Job cleanup mechanism (in-memory jobs leak)
- [ ] Content Security Policy headers

### Low Priority
- [ ] Multiple embedding model support
- [ ] Re-embed with different model
- [ ] Custom chunk sizes per source
- [ ] Scheduled re-crawls
- [ ] Memory importance decay (cron-based)
- [ ] Table partitioning for high-volume episodic memories

### Performance
- [ ] Index optimization for filtered vector search
- [ ] Caching for frequent queries
- [ ] Async embedding generation
- [ ] Connection pooling for Supabase

---

## Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Embeddings | Ollama + nomic-embed-text | Local, free, 768-dim |
| Vector DB | Supabase + pgvector | Self-hosted, SQL, RLS |
| Backend | FastAPI | Async, fast, typed |
| Frontend | HTMX + Tailwind | No build step |
| Interactivity | Alpine.js | Lightweight |
| Doc Parsing | Docling | IBM, comprehensive |
| Web Crawling | BeautifulSoup + html2text | Standard, reliable |
| Auth | pgcrypto + API keys | Simple, agent-friendly |
