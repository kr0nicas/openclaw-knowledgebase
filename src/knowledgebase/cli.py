"""Command-line interface for OpenClaw Knowledgebase."""

import sys
import time
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from knowledgebase.config import get_config
from knowledgebase.client import KnowledgeBase
from knowledgebase.embeddings import get_embedding, test_connection, list_providers
from knowledgebase.search import search, search_hybrid, format_results

console = Console()


@click.group()
@click.version_option(version="0.2.0")
def main():
    """OpenClaw Knowledgebase - Self-hosted RAG with multi-agent memory."""
    pass


@main.command()
def status():
    """Check connection status and show statistics."""
    config = get_config()

    console.print("\n[bold]OpenClaw Knowledgebase Status[/bold]\n")

    # Check embedding provider
    console.print(f"  Provider: [cyan]{config.embedding_provider}[/cyan] ({config.embedding_model})")
    ok, msg = test_connection()
    if ok:
        console.print(f"  ✅ Embeddings: {msg}")
    else:
        console.print(f"  ❌ Embeddings: {msg}")

    # Check Supabase
    try:
        kb = KnowledgeBase()
        stats = kb.stats()
        console.print(f"  ✅ Supabase: Connected")
        console.print()

        table = Table(title="Knowledge Base Stats")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        table.add_row("Sources", str(stats.get("total_sources", 0)))
        table.add_row("Total Chunks", str(stats.get("total_chunks", 0)))
        table.add_row("With Embeddings", str(stats.get("chunks_with_embeddings", 0)))
        table.add_row("Without Embeddings", str(stats.get("chunks_without_embeddings", 0)))

        console.print(table)
    except Exception as e:
        console.print(f"  ❌ Supabase: {e}")

    console.print()


@main.command()
@click.argument("query")
@click.option("-n", "--limit", default=5, help="Number of results")
@click.option("-t", "--threshold", default=0.5, help="Similarity threshold")
@click.option("--hybrid", is_flag=True, help="Use hybrid search")
def find(query: str, limit: int, threshold: float, hybrid: bool):
    """Search the knowledge base."""
    console.print(f"\n🔍 Searching: [cyan]{query}[/cyan]\n")

    if hybrid:
        results = search_hybrid(query, limit=limit)
    else:
        results = search(query, limit=limit, threshold=threshold)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    for i, r in enumerate(results, 1):
        sim = r.get("similarity", 0)
        title = r.get("title") or "Untitled"
        url = r.get("url", "")
        content = r.get("content", "")[:300]

        console.print(f"[bold]{i}.[/bold] [{sim:.2f}] [cyan]{title}[/cyan]")
        console.print(f"   [dim]{url}[/dim]")
        console.print(f"   {content}...")
        console.print()


@main.command()
@click.option("--batch-size", default=50, help="Chunks per batch")
def embed(batch_size: int):
    """Generate embeddings for chunks that don't have them."""
    config = get_config()
    kb = KnowledgeBase()

    # Check provider first
    ok, msg = test_connection()
    if not ok:
        console.print(f"[red]❌ {msg}[/red]")
        sys.exit(1)

    console.print(f"  Provider: [cyan]{config.embedding_provider}[/cyan] ({config.embedding_model})")

    total_without = kb.count_chunks(with_embeddings=False)
    if total_without == 0:
        console.print("[green]✅ All chunks have embeddings![/green]")
        return

    console.print(f"\n🧠 Generating embeddings for {total_without} chunks...\n")

    total_done = 0
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Embedding...", total=total_without)

        while True:
            chunks = kb.get_chunks_without_embeddings(limit=batch_size)
            if not chunks:
                break

            for chunk in chunks:
                embedding = get_embedding(chunk.content)
                if embedding:
                    kb.update_chunk_embedding(chunk.id, embedding)
                    total_done += 1

                progress.update(task, advance=1)

                elapsed = time.time() - start_time
                rate = total_done / elapsed if elapsed > 0 else 0
                progress.update(task, description=f"Embedding... ({rate:.1f}/s)")

    elapsed = time.time() - start_time
    console.print(f"\n[green]✅ Done![/green] {total_done} embeddings in {elapsed:.0f}s")


@main.command()
def sources():
    """List all sources in the knowledge base."""
    kb = KnowledgeBase()
    src_list = kb.list_sources()

    if not src_list:
        console.print("[yellow]No sources found.[/yellow]")
        return

    table = Table(title="Knowledge Base Sources")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Title")
    table.add_column("URL", style="dim", max_width=50)

    for s in src_list:
        table.add_row(
            str(s.id),
            s.source_type,
            s.title or "-",
            s.url[:50] + "..." if len(s.url) > 50 else s.url,
        )

    console.print(table)


@main.command()
def providers():
    """List available embedding providers."""
    config = get_config()
    active = config.embedding_provider

    console.print("\n[bold]Embedding Providers[/bold]\n")
    for name in list_providers():
        marker = " [green](active)[/green]" if name == active else ""
        console.print(f"  • {name}{marker}")
    console.print()
    console.print("  Set EMBEDDING_PROVIDER in .env to switch.\n")


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8080, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload (dev)")
def serve(host: str, port: int, reload: bool):
    """Start the web UI server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]❌ Web dependencies not installed.[/red]")
        console.print("Install with: [cyan]pip install openclaw-knowledgebase[web][/cyan]")
        sys.exit(1)

    console.print(f"\n🚀 Starting web UI at [cyan]http://{host}:{port}[/cyan]\n")

    uvicorn.run(
        "knowledgebase.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
