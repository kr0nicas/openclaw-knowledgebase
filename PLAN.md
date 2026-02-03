# OpenClaw Knowledgebase - Entwicklungsplan

## Übersicht

Vier Features werden hinzugefügt:
1. **Docling-Parser** - PDF/DOCX/PPTX Ingestion
2. **Web-Crawler** - URLs crawlen und indexieren
3. **OpenClaw Skill** - Automatische Nutzung durch Agents
4. **Web-UI** - Benutzeroberfläche für Suche & Verwaltung

---

## 1. Docling-Parser 📄

**Ziel:** Lokale Dokumente (PDF, DOCX, PPTX, etc.) parsen und in die KB aufnehmen.

**Dateien:**
- `src/knowledgebase/ingest/docling_parser.py`
- `src/knowledgebase/ingest/chunker.py`

**Funktionen:**
```python
# docling_parser.py
def parse_document(path: Path) -> Document
def parse_directory(path: Path, recursive: bool = True) -> list[Document]

# chunker.py  
def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]
def chunk_document(doc: Document) -> list[Chunk]
```

**CLI-Befehle:**
```bash
kb ingest ./documents/           # Verzeichnis
kb ingest ./manual.pdf           # Einzelne Datei
kb ingest ./docs/ --recursive    # Rekursiv
```

**Dependencies:**
- `docling>=2.0.0` (optional, für PDF/DOCX)
- Fallback: Nur Markdown/TXT ohne Docling

---

## 2. Web-Crawler 🕷️

**Ziel:** Webseiten crawlen, in Markdown konvertieren, chunken und indexieren.

**Dateien:**
- `src/knowledgebase/ingest/crawler.py`

**Funktionen:**
```python
def crawl_url(url: str, max_depth: int = 1) -> list[Page]
def crawl_sitemap(sitemap_url: str) -> list[Page]
def html_to_markdown(html: str) -> str
```

**CLI-Befehle:**
```bash
kb crawl https://docs.example.com              # Einzelne Seite
kb crawl https://docs.example.com --depth 2    # Mit Unterseiten
kb crawl https://example.com/sitemap.xml       # Via Sitemap
```

**Dependencies:**
- `beautifulsoup4>=4.12.0`
- `html2text>=2024.2.26`
- `requests` (bereits vorhanden)

**Features:**
- Respektiert robots.txt
- Rate-Limiting (1 req/sec default)
- Duplicate Detection (URL + Content Hash)
- Incremental Updates (nur neue/geänderte Seiten)

---

## 3. OpenClaw Skill 🦞

**Ziel:** Agents können die KB automatisch durchsuchen.

**Dateien:**
- `skills/knowledgebase/SKILL.md`
- `skills/knowledgebase/search.sh` (oder Python wrapper)

**SKILL.md Inhalt:**
```markdown
# Knowledgebase Skill

Durchsuche die lokale Wissensdatenbank für relevante Informationen.

## Verwendung
- Nutze `kb find "query"` für semantische Suche
- Nutze `kb find "query" --hybrid` für kombinierte Suche

## Wann nutzen
- Bei Fragen zu Home Assistant, Dokumentation, etc.
- Bevor du im Web suchst - lokale KB ist schneller und relevanter
```

**Integration:**
- Skill in `~/clawd/skills/knowledgebase/` installieren
- Oder als Teil des Repos unter `skills/`

---

## 4. Web-UI 🖥️

**Ziel:** Benutzerfreundliche Oberfläche für Suche und Verwaltung.

**Tech-Stack:**
- **Backend:** FastAPI (Python, bereits im Projekt)
- **Frontend:** HTMX + Tailwind + Alpine.js (minimal, kein Build-Step)
- **Icons:** Lucide Icons (wie Archon)

**Design-Inspiration von Archon UI:**
- Glassmorphism (blur + semi-transparent)
- Edge Colors je nach Status
- Type Badges (Web/Document, Technical/Business)
- Stat Pills für Counts
- Grid/Table View Toggle
- Inline Progress Tracking

**Dateien:**
- `src/knowledgebase/web/app.py` - FastAPI App
- `src/knowledgebase/web/templates/` - Jinja2 Templates
- `src/knowledgebase/web/static/` - CSS/JS

**Seiten:**
1. **Dashboard** (`/`)
   - Stats (Sources, Chunks, Embeddings)
   - Quick Search Box
   - Recent Activity

2. **Search** (`/search`)
   - Suchfeld mit Live-Results
   - Filter: Source, Date, Similarity Threshold
   - Result Preview mit Highlighting

3. **Sources** (`/sources`)
   - Liste aller Sources
   - Add new URL / Upload Document
   - Delete / Re-crawl Actions

4. **Settings** (`/settings`)
   - Ollama URL/Model
   - Chunk Size/Overlap
   - Re-embed All Button

**CLI-Befehl:**
```bash
kb serve                    # Start auf http://localhost:8080
kb serve --port 3000        # Custom Port
kb serve --host 0.0.0.0     # Expose im Netzwerk
```

**Wireframe Dashboard:**
```
┌─────────────────────────────────────────────────────────┐
│  🦞 OpenClaw Knowledgebase                    [Settings]│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 🔍 Search your knowledge base...            [⏎] │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Sources  │ │  Chunks  │ │ Embedded │ │ Pending  │  │
│  │    8     │ │   1100   │ │   1081   │ │    19    │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                         │
│  Recent Sources                          [+ Add Source] │
│  ├─ 📄 Home Assistant Docs      1,050 chunks    ✅     │
│  ├─ 📄 Pydantic Docs              320 chunks    ✅     │
│  ├─ 📄 Supabase Docs              180 chunks    ✅     │
│  └─ ...                                                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Reihenfolge & Zeitplan

| # | Feature | Abhängigkeiten | Geschätzte Zeit |
|---|---------|----------------|-----------------|
| 1 | Chunker | - | 15 min |
| 2 | Web-Crawler | Chunker | 30 min |
| 3 | Docling-Parser | Chunker | 30 min |
| 4 | OpenClaw Skill | - | 10 min |
| 5 | Web-UI Backend | - | 45 min |
| 6 | Web-UI Frontend | Backend | 45 min |

**Total: ~3 Stunden**

---

## Abnahmekriterien

- [ ] `kb ingest ./file.pdf` funktioniert
- [ ] `kb crawl https://example.com` funktioniert
- [ ] Jarvis kann Skill nutzen für automatische Suche
- [ ] Web-UI zeigt Dashboard mit Stats
- [ ] Web-UI Suche liefert Ergebnisse mit Highlighting
- [ ] Web-UI kann neue URLs hinzufügen
- [ ] Alle Features dokumentiert in README

---

*Plan erstellt: 2026-02-03*
