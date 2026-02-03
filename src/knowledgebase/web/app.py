"""FastAPI web application for OpenClaw Knowledgebase."""

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from knowledgebase.client import KnowledgeBase
from knowledgebase.config import get_config
from knowledgebase.embeddings import test_ollama_connection, get_embedding
from knowledgebase.search import search, search_hybrid

# Paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="OpenClaw Knowledgebase",
        description="Self-hosted RAG with Ollama + Supabase",
        version="0.1.0",
    )
    
    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    
    # Templates
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    
    # Add custom template functions
    def format_similarity(value: float) -> str:
        return f"{value:.0%}" if value else "N/A"
    
    templates.env.filters["similarity"] = format_similarity
    
    # --- Routes ---
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Dashboard with stats and quick search."""
        kb = KnowledgeBase()
        stats = kb.stats()
        sources = kb.list_sources(limit=10)
        
        # Check connections
        ollama_ok, ollama_msg = test_ollama_connection()
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "stats": stats,
            "sources": sources,
            "ollama_ok": ollama_ok,
            "ollama_msg": ollama_msg,
        })
    
    @app.get("/search", response_class=HTMLResponse)
    async def search_page(
        request: Request,
        q: str = Query(default=""),
        hybrid: bool = Query(default=False),
        limit: int = Query(default=10),
    ):
        """Search page with results."""
        results = []
        
        if q:
            if hybrid:
                results = search_hybrid(q, limit=limit)
            else:
                results = search(q, limit=limit)
        
        return templates.TemplateResponse("search.html", {
            "request": request,
            "query": q,
            "hybrid": hybrid,
            "limit": limit,
            "results": results,
        })
    
    @app.post("/search", response_class=HTMLResponse)
    async def search_post(
        request: Request,
        q: str = Form(...),
        hybrid: bool = Form(default=False),
        limit: int = Form(default=10),
    ):
        """Handle search form submission."""
        return RedirectResponse(
            url=f"/search?q={q}&hybrid={hybrid}&limit={limit}",
            status_code=303,
        )
    
    @app.get("/htmx/search-results", response_class=HTMLResponse)
    async def htmx_search_results(
        request: Request,
        q: str = Query(default=""),
        hybrid: bool = Query(default=False),
        limit: int = Query(default=10),
    ):
        """HTMX endpoint for live search results."""
        results = []
        
        if q and len(q) >= 2:
            if hybrid:
                results = search_hybrid(q, limit=limit)
            else:
                results = search(q, limit=limit)
        
        return templates.TemplateResponse("partials/search_results.html", {
            "request": request,
            "results": results,
            "query": q,
        })
    
    @app.get("/sources", response_class=HTMLResponse)
    async def sources_page(request: Request):
        """Sources management page."""
        kb = KnowledgeBase()
        sources = kb.list_sources(limit=100)
        
        return templates.TemplateResponse("sources.html", {
            "request": request,
            "sources": sources,
        })
    
    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        """Settings page."""
        config = get_config()
        ollama_ok, ollama_msg = test_ollama_connection()
        
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "config": config,
            "ollama_ok": ollama_ok,
            "ollama_msg": ollama_msg,
        })
    
    # --- API Endpoints ---
    
    @app.get("/api/stats")
    async def api_stats():
        """Get knowledge base statistics."""
        kb = KnowledgeBase()
        return kb.stats()
    
    @app.get("/api/search")
    async def api_search(
        q: str = Query(...),
        hybrid: bool = Query(default=False),
        limit: int = Query(default=10),
        threshold: float = Query(default=0.5),
    ):
        """Search API endpoint."""
        if hybrid:
            return search_hybrid(q, limit=limit)
        return search(q, limit=limit, threshold=threshold)
    
    @app.get("/api/sources")
    async def api_sources(limit: int = Query(default=100)):
        """List sources."""
        kb = KnowledgeBase()
        sources = kb.list_sources(limit=limit)
        return [
            {
                "id": s.id,
                "url": s.url,
                "title": s.title,
                "source_type": s.source_type,
            }
            for s in sources
        ]
    
    @app.get("/api/health")
    async def api_health():
        """Health check endpoint."""
        ollama_ok, ollama_msg = test_ollama_connection()
        return {
            "status": "ok" if ollama_ok else "degraded",
            "ollama": {"ok": ollama_ok, "message": ollama_msg},
        }
    
    return app


# Create app instance for uvicorn
app = create_app()
