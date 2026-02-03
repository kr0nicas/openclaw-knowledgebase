# 🦞 OpenClaw Knowledgebase

A simple, self-hosted RAG (Retrieval-Augmented Generation) system using **Ollama** for local embeddings and **Supabase/pgvector** for vector storage.

**100% local. 100% free. No OpenAI API needed.**

## ✨ Features

- 🔒 **Fully Local** - Embeddings via Ollama, self-hosted Supabase
- 💸 **Zero Cost** - No API fees, runs on your hardware
- 🔍 **Hybrid Search** - Semantic + keyword search combined
- 🌐 **Web UI** - Beautiful dashboard with live search
- 📄 **Multi-Format** - PDFs, DOCX, URLs, Markdown (via Docling)
- ⚡ **Fast** - ~4 embeddings/second on Apple Silicon
- 🧩 **OpenClaw Ready** - Designed for [OpenClaw](https://github.com/openclaw/openclaw) AI agents

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) running locally or on your network
- [Supabase](https://supabase.com) (self-hosted or cloud) with pgvector

### Installation

```bash
# Clone the repo
git clone https://github.com/f2daz/openclaw-knowledgebase.git
cd openclaw-knowledgebase

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .

# For web UI (optional)
pip install -e ".[web]"

# For all features
pip install -e ".[all]"
```

### Setup

1. **Pull the embedding model:**
```bash
ollama pull nomic-embed-text
```

2. **Create the database schema:**
```bash
# Run schema.sql in your Supabase SQL editor
# Or via psql:
psql $DATABASE_URL -f schema.sql
```

3. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your Supabase URL, key, and Ollama URL
```

## 📖 CLI Commands

```bash
# Check status and connections
kb status

# Search semantically
kb find "How do I create an automation?"

# Hybrid search (semantic + keyword)
kb find "zigbee2mqtt pairing" --hybrid

# More results
kb find "home assistant" -n 20

# List all sources
kb sources

# Generate embeddings for new chunks
kb embed --batch-size 50

# Start web UI
kb serve --port 8080
```

## 🌐 Web UI

Start the web UI with:

```bash
kb serve
```

Then open http://localhost:8080

Features:
- 📊 **Dashboard** - Stats overview, connection status
- 🔍 **Live Search** - Real-time semantic search with HTMX
- 📁 **Sources** - Browse and manage your knowledge sources
- ⚙️ **Settings** - View configuration and status

![Dashboard](docs/dashboard.png)

## 📐 Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Sources   │────▶│   Parser    │────▶│   Chunks    │
│ PDF/URL/... │     │  Docling    │     │  Markdown   │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Search    │◀────│  Supabase   │◀────│   Ollama    │
│   Results   │     │  pgvector   │     │  Embeddings │
└─────────────┘     └─────────────┘     └─────────────┘
```

## 🗄️ Database Schema

Two main tables:
- `{prefix}_sources` - Tracked URLs/documents with metadata
- `{prefix}_chunks` - Text chunks with 768-dim embeddings

Search functions:
- `{prefix}_search_semantic()` - Pure vector similarity
- `{prefix}_search_hybrid()` - Combined semantic + keyword

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase REST API URL | - |
| `SUPABASE_KEY` | Supabase service key | - |
| `TABLE_PREFIX` | Prefix for tables (`kb` → `kb_sources`) | `kb` |
| `OLLAMA_URL` | Ollama API URL | `http://localhost:11434` |
| `EMBEDDING_MODEL` | Ollama embedding model | `nomic-embed-text` |
| `CHUNK_SIZE` | Characters per chunk | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `200` |

> **Tip:** Use `TABLE_PREFIX=jarvis` if you have existing `jarvis_sources`/`jarvis_chunks` tables.

## 🔌 Python API

```python
from knowledgebase import search, search_hybrid, KnowledgeBase

# Quick semantic search
results = search("home assistant automation", limit=5)
for r in results:
    print(f"[{r['similarity']:.2f}] {r['title']}")
    print(f"  {r['content'][:200]}...")

# Hybrid search (better for specific terms)
results = search_hybrid("zigbee pairing", limit=5)

# Full client access
kb = KnowledgeBase()
stats = kb.stats()
sources = kb.list_sources()
```

## 🧩 OpenClaw Skill

A skill is included at `skills/knowledgebase/SKILL.md` for easy integration with OpenClaw agents:

```bash
# Copy to your OpenClaw skills folder
cp -r skills/knowledgebase ~/clawd/skills/
```

## 📦 Optional Dependencies

```bash
# Document parsing (PDF, DOCX, etc.)
pip install openclaw-knowledgebase[docling]

# Web crawling
pip install openclaw-knowledgebase[crawl]

# Web UI
pip install openclaw-knowledgebase[web]

# Everything
pip install openclaw-knowledgebase[all]
```

## 📊 Embedding Models

| Model | Dimensions | Speed | Quality |
|-------|-----------|-------|---------|
| `nomic-embed-text` | 768 | ⚡⚡⚡ | ⭐⭐⭐ |
| `mxbai-embed-large` | 1024 | ⚡⚡ | ⭐⭐⭐⭐ |
| `all-minilm` | 384 | ⚡⚡⚡⚡ | ⭐⭐ |

Default: `nomic-embed-text` - best balance of speed and quality.

## 🤝 Contributing

PRs welcome! Please open an issue first to discuss larger changes.

## 📄 License

MIT License - see [LICENSE](LICENSE)

## 🙏 Credits

- [Ollama](https://ollama.ai) - Local LLM inference
- [Supabase](https://supabase.com) - Postgres + pgvector
- [Docling](https://github.com/docling-project/docling) - Document parsing
- [OpenClaw](https://github.com/openclaw/openclaw) - AI agent framework
- [HTMX](https://htmx.org) - Web UI interactions
- [Tailwind CSS](https://tailwindcss.com) - Styling

---

Built with 🦞 by the OpenClaw community
