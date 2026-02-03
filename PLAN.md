# OpenClaw Knowledgebase - Development Plan

## Status: v0.1.0 Released ✅

### Completed Features

#### 1. Core Infrastructure ✅
- [x] Supabase client with configurable table prefix
- [x] Ollama embedding integration
- [x] Semantic search via RPC functions
- [x] Hybrid search (semantic + keyword)
- [x] Fallback client-side vector search
- [x] Stats and health endpoints

#### 2. Ingestion Pipeline ✅
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

#### 3. CLI ✅
- [x] `kb status` - Check connections
- [x] `kb find` - Search with options
- [x] `kb sources` - List sources
- [x] `kb embed` - Generate embeddings
- [x] `kb serve` - Start web UI

#### 4. Web UI ✅
- [x] Dashboard with stats
- [x] Live search with HTMX
- [x] Sources list with delete
- [x] Add Source modal (crawl/upload)
- [x] Settings page
- [x] Glassmorphism design (Archon-inspired)

#### 5. OpenClaw Skill ✅
- [x] SKILL.md with usage instructions
- [x] Search workflow examples

---

## Future Improvements

### High Priority ✅
- [x] Source refresh/re-crawl action
- [x] Progress bar for long operations (Toast)
- [x] Chunk preview in search results (with expand)
- [x] Query term highlighting

### Medium Priority ✅
- [x] Tags for sources (add/remove/filter)
- [x] Search filters (threshold)
- [x] Type filter (All/Web/Documents)
- [x] Export search results (JSON/Markdown/CSV)
- [x] Source details page (with all chunks)

### Still TODO
- [ ] Better error messages in UI
- [ ] Batch delete/operations

### Low Priority
- [ ] Multiple embedding models
- [ ] Re-embed with different model
- [ ] Custom chunk sizes per source
- [ ] Scheduled re-crawls
- [ ] Webhooks for new content

### Performance
- [ ] Proper pgvector search function
- [ ] Index optimization
- [ ] Caching for frequent queries
- [ ] Async embedding generation

---

## Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Embeddings | Ollama + nomic-embed-text | Local, free, 768-dim |
| Vector DB | Supabase + pgvector | Self-hosted, SQL |
| Backend | FastAPI | Async, fast, typed |
| Frontend | HTMX + Tailwind | No build step |
| Interactivity | Alpine.js | Lightweight |
| Doc Parsing | Docling | IBM, comprehensive |
| Web Crawling | BeautifulSoup + html2text | Standard, reliable |

---

## Schema Compatibility

The codebase supports different Supabase schemas:

### New Schema (`kb_*`)
- Uses `schema.sql` provided
- Full feature support

### Archon Schema (`jarvis_*`)
- Different column names (`chunk_index` vs `chunk_number`)
- No `url`/`title` in chunks (stored in metadata)
- Uses RPC functions for search
- Fallback to client-side search if needed

Set `TABLE_PREFIX=jarvis` in `.env` to use Archon tables.
