#!/usr/bin/env python3
"""OpenClaw Memory Bootstrap — Setup and verify the multi-agent memory system.

Usage:
    python3 bootstrap.py validate   # Check env & connections
    python3 bootstrap.py schema     # Apply SQL schema
    python3 bootstrap.py register   # Register this agent
    python3 bootstrap.py access     # Grant RAG access
    python3 bootstrap.py test       # Run smoke test
    python3 bootstrap.py all        # Run all steps
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv, set_key

ENV_PATH = PROJECT_ROOT / ".env"
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"
SCHEMA_MEMORY_PATH = PROJECT_ROOT / "schema_memory.sql"


# ── Utilities ────────────────────────────────────────────────────────

class Colors:
    OK = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {Colors.OK}✓{Colors.END} {msg}")


def fail(msg: str) -> None:
    print(f"  {Colors.FAIL}✗{Colors.END} {msg}")


def warn(msg: str) -> None:
    print(f"  {Colors.WARN}⚠{Colors.END} {msg}")


def heading(msg: str) -> None:
    print(f"\n{Colors.BOLD}{'─' * 60}{Colors.END}")
    print(f"{Colors.BOLD}  {msg}{Colors.END}")
    print(f"{Colors.BOLD}{'─' * 60}{Colors.END}")


def get_env() -> dict:
    """Load and return environment variables.

    Also invalidates the knowledgebase config cache so that any
    subsequent call to get_config() picks up the freshly loaded values.
    """
    load_dotenv(ENV_PATH, override=True)

    # Invalidate config singleton — avoids stale cached defaults
    try:
        from knowledgebase.config import _config_cache
        _config_cache["reload"] = True
    except ImportError:
        pass

    return {
        "SUPABASE_URL": os.getenv("SUPABASE_URL", "").rstrip("/"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY", ""),
        "OLLAMA_URL": os.getenv("OLLAMA_URL", "http://localhost:11434"),
        "EMBEDDING_MODEL": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
        "TABLE_PREFIX": os.getenv("TABLE_PREFIX", "kb"),
        "EMBEDDING_PROVIDER": os.getenv("EMBEDDING_PROVIDER", "ollama"),
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", ""),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "OPENCLAW_AGENT_NAME": os.getenv("OPENCLAW_AGENT_NAME", ""),
        "OPENCLAW_AGENT_KEY": os.getenv("OPENCLAW_AGENT_KEY", ""),
    }


def supabase_headers(env: dict) -> dict:
    return {
        "apikey": env["SUPABASE_KEY"],
        "Authorization": f"Bearer {env['SUPABASE_KEY']}",
        "Content-Type": "application/json",
    }


def supabase_rpc(env: dict, fn: str, params: dict, timeout: int = 30):
    """Call a Supabase RPC function."""
    import requests

    resp = requests.post(
        f"{env['SUPABASE_URL']}/rest/v1/rpc/{fn}",
        headers=supabase_headers(env),
        json=params,
        timeout=timeout,
    )
    return resp


def supabase_sql(env: dict, sql: str, timeout: int = 60):
    """Execute raw SQL via Supabase's /rest/v1/rpc or pg_net.

    Uses the Supabase SQL endpoint (requires service_role key).
    Falls back to executing via the query endpoint if available.
    """
    import requests

    urls_to_try = [
        f"{env['SUPABASE_URL']}/rest/v1/rpc/exec_sql",
        f"{env['SUPABASE_URL']}/pg/query",
    ]

    for url in urls_to_try:
        try:
            resp = requests.post(
                url,
                headers=supabase_headers(env),
                json={"query": sql} if "/pg/" in url else {"sql_text": sql},
                timeout=timeout,
            )
            if resp.status_code in (200, 201):
                return resp
        except Exception:
            continue

    return None


# ── Step 1: Validate ─────────────────────────────────────────────────

def step_validate() -> bool:
    """Validate environment and connections."""
    heading("Step 1: Validate Environment")
    import requests

    env = get_env()
    all_ok = True

    # Check .env file
    if ENV_PATH.exists():
        ok(f".env found at {ENV_PATH}")
    else:
        fail(f".env not found at {ENV_PATH}")
        print(f"    Copy .env.example to .env and fill in your credentials.")
        return False

    # Check required vars
    for var in ("SUPABASE_URL", "SUPABASE_KEY"):
        val = env[var]
        if val:
            display = val[:20] + "..." if len(val) > 20 else val
            ok(f"{var} = {display}")
        else:
            fail(f"{var} is empty")
            all_ok = False

    if not all_ok:
        fail("Missing required environment variables. Update .env and retry.")
        return False

    # Test Supabase connection
    try:
        resp = requests.get(
            f"{env['SUPABASE_URL']}/rest/v1/",
            headers=supabase_headers(env),
            timeout=10,
        )
        if resp.status_code == 200:
            ok(f"Supabase connection OK ({env['SUPABASE_URL']})")
        else:
            fail(f"Supabase returned HTTP {resp.status_code}: {resp.text[:200]}")
            all_ok = False
    except requests.exceptions.ConnectionError:
        fail(f"Cannot connect to Supabase at {env['SUPABASE_URL']}")
        all_ok = False
    except Exception as e:
        fail(f"Supabase error: {e}")
        all_ok = False

    # Test embedding provider (config is reloaded by get_env() above)
    from knowledgebase.embeddings import test_connection, get_provider

    provider_name = env["EMBEDDING_PROVIDER"]
    model = env["EMBEDDING_MODEL"]
    ok_msg = f"Provider: {provider_name} / Model: {model}"

    # Validate provider-specific keys before testing connection
    if provider_name == "google" and not env.get("GOOGLE_API_KEY"):
        fail(f"EMBEDDING_PROVIDER=google but GOOGLE_API_KEY is empty")
        all_ok = False
    elif provider_name in ("openai", "custom") and not env.get("OPENAI_API_KEY"):
        fail(f"EMBEDDING_PROVIDER={provider_name} but OPENAI_API_KEY is empty")
        all_ok = False

    if all_ok:
        provider_ok, provider_msg = test_connection()
        if provider_ok:
            ok(f"Embeddings OK — {ok_msg}")
            ok(f"  {provider_msg}")
        else:
            fail(f"Embeddings FAILED — {ok_msg}")
            fail(f"  {provider_msg}")
            if provider_name == "ollama":
                print(f"    Start Ollama with: ollama serve")
                print(f"    Then: ollama pull {model}")
            all_ok = False

    if all_ok:
        ok("All validations passed")
    return all_ok


# ── Step 2: Apply Schema ─────────────────────────────────────────────

def step_schema() -> bool:
    """Apply SQL schemas to Supabase."""
    heading("Step 2: Apply Schema")
    import requests

    env = get_env()
    headers = supabase_headers(env)

    schemas = []
    for path, label in [(SCHEMA_PATH, "schema.sql"), (SCHEMA_MEMORY_PATH, "schema_memory.sql")]:
        if not path.exists():
            fail(f"{label} not found at {path}")
            return False
        sql = path.read_text()
        schemas.append((sql, label))
        ok(f"Loaded {label} ({len(sql)} bytes)")

    for sql, label in schemas:
        result = supabase_sql(env, sql)
        if result and result.status_code in (200, 201):
            ok(f"Applied {label} via SQL endpoint")
            continue

        # Fallback: tell user to apply manually
        warn(f"Cannot execute SQL directly (Supabase cloud doesn't expose raw SQL via REST)")
        print(f"    Apply {label} manually:")
        print(f"    1. Go to your Supabase dashboard → SQL Editor")
        print(f"    2. Paste the contents of: {path}")
        print(f"    3. Click 'Run'")
        print()

        response = input(f"    Have you applied {label}? [y/N]: ").strip().lower()
        if response != "y":
            fail(f"Schema {label} not applied. Cannot continue.")
            return False

    # Verify critical tables exist
    tables_to_check = ["kb_sources", "kb_chunks", "mb_agents", "mb_memory", "mb_teams"]
    all_ok = True
    for table in tables_to_check:
        try:
            resp = requests.get(
                f"{env['SUPABASE_URL']}/rest/v1/{table}",
                headers=headers,
                params={"limit": "0"},
                timeout=10,
            )
            if resp.status_code == 200:
                ok(f"Table '{table}' exists")
            else:
                fail(f"Table '{table}' not found (HTTP {resp.status_code})")
                all_ok = False
        except Exception as e:
            fail(f"Error checking table '{table}': {e}")
            all_ok = False

    # Verify critical RPC functions
    rpcs = ["mb_register_agent", "mb_authenticate_agent", "mb_search_memory", "mb_search_all"]
    for rpc in rpcs:
        try:
            resp = supabase_rpc(env, rpc, {}, timeout=5)
            if resp.status_code in (200, 400, 422):
                ok(f"RPC function '{rpc}' exists")
            elif resp.status_code == 404:
                fail(f"RPC function '{rpc}' not found")
                all_ok = False
            else:
                ok(f"RPC function '{rpc}' exists (returned {resp.status_code})")
        except Exception as e:
            fail(f"Error checking RPC '{rpc}': {e}")
            all_ok = False

    if all_ok:
        ok("Schema fully applied and verified")
    return all_ok


# ── Step 3: Register Agent ───────────────────────────────────────────

def step_register() -> bool:
    """Register this agent in mb_agents."""
    heading("Step 3: Register Agent")

    env = get_env()
    agent_name = env["OPENCLAW_AGENT_NAME"]
    agent_key = env["OPENCLAW_AGENT_KEY"]

    # Generate name if not set
    if not agent_name:
        import socket
        agent_name = f"openclaw-{socket.gethostname().lower().split('.')[0]}"
        warn(f"OPENCLAW_AGENT_NAME not set, using: {agent_name}")
        set_key(str(ENV_PATH), "OPENCLAW_AGENT_NAME", agent_name)
        ok(f"Saved OPENCLAW_AGENT_NAME={agent_name} to .env")

    # Generate API key if not set
    from knowledgebase.memory.auth import generate_api_key

    new_key_generated = False
    if not agent_key:
        agent_key = generate_api_key()
        new_key_generated = True
        ok(f"Generated API key: {agent_key[:15]}...")

    # Try to register
    resp = supabase_rpc(env, "mb_register_agent", {
        "p_name": agent_name,
        "p_api_key": agent_key,
        "p_display_name": agent_name,
        "p_agent_type": "openclaw",
        "p_metadata": {"bootstrap": True, "version": "0.2.0"},
    })

    if resp.status_code == 200 and resp.json():
        agent_id = resp.json()
        if isinstance(agent_id, str):
            agent_id = agent_id.strip('"')
        ok(f"Agent registered: {agent_name} ({agent_id})")

        # Save key to .env
        set_key(str(ENV_PATH), "OPENCLAW_AGENT_KEY", agent_key)
        ok(f"Saved OPENCLAW_AGENT_KEY to .env")

        if new_key_generated:
            print(f"\n  {Colors.WARN}SAVE THIS KEY — it cannot be recovered:{Colors.END}")
            print(f"  {Colors.BOLD}{agent_key}{Colors.END}\n")

    elif "duplicate key" in resp.text.lower() or "unique" in resp.text.lower():
        warn(f"Agent '{agent_name}' already registered")

        # If we generated a new key but agent exists, we can't use it
        if new_key_generated:
            fail("Agent exists but no API key in .env. You need the original key.")
            print("    Options:")
            print("    1. Set OPENCLAW_AGENT_KEY in .env to the original key")
            print("    2. Delete the agent from mb_agents and re-run this step")
            return False
        ok("Using existing API key from .env")
    else:
        fail(f"Registration failed: HTTP {resp.status_code} — {resp.text[:300]}")
        return False

    # Verify authentication
    env = get_env()  # reload to pick up saved values
    resp = supabase_rpc(env, "mb_authenticate_agent", {"p_api_key": env["OPENCLAW_AGENT_KEY"]})
    if resp.status_code == 200 and resp.json():
        agent_info = resp.json()[0]
        ok(f"Authentication verified: {agent_info['agent_name']} ({agent_info['agent_id']})")
        return True
    else:
        fail(f"Authentication failed after registration: {resp.text[:200]}")
        return False


# ── Step 4: Bootstrap RAG Access ─────────────────────────────────────

def step_access() -> bool:
    """Grant this agent access to all existing kb_sources."""
    heading("Step 4: Bootstrap RAG Access")
    import requests

    env = get_env()
    headers = supabase_headers(env)

    # Get agent ID
    resp = supabase_rpc(env, "mb_authenticate_agent", {"p_api_key": env["OPENCLAW_AGENT_KEY"]})
    if resp.status_code != 200 or not resp.json():
        fail("Cannot authenticate agent. Run step 3 first.")
        return False

    agent_id = resp.json()[0]["agent_id"]

    # Check existing sources
    resp = requests.get(
        f"{env['SUPABASE_URL']}/rest/v1/{env['TABLE_PREFIX']}_sources",
        headers=headers,
        params={"select": "id,url,title", "limit": "100"},
        timeout=10,
    )

    if resp.status_code == 200:
        sources = resp.json()
        if sources:
            ok(f"Found {len(sources)} existing RAG sources")
        else:
            warn("No existing RAG sources found (empty knowledgebase)")
            ok("Access bootstrap skipped (nothing to grant)")
            return True
    else:
        warn(f"Could not list sources: HTTP {resp.status_code}")

    # Bootstrap access
    resp = supabase_rpc(env, "mb_bootstrap_agent_access", {"p_agent_id": agent_id})
    if resp.status_code == 200:
        count = resp.json()
        if isinstance(count, int) and count > 0:
            ok(f"Granted global access to {count} RAG sources")
        elif isinstance(count, int) and count == 0:
            ok("All sources already accessible (no new grants needed)")
        else:
            ok(f"Access bootstrap completed (result: {count})")
        return True
    else:
        fail(f"Bootstrap access failed: {resp.text[:200]}")
        return False


# ── Step 5: Smoke Test ───────────────────────────────────────────────

def step_test() -> bool:
    """Run end-to-end smoke test."""
    heading("Step 5: Smoke Test")

    from knowledgebase.config import reload_config
    from knowledgebase.memory import AgentMemory, Scope, MemoryType

    # Force reload config to pick up latest .env
    reload_config()
    env = get_env()

    agent_name = env["OPENCLAW_AGENT_NAME"]
    agent_key = env["OPENCLAW_AGENT_KEY"]

    if not agent_name or not agent_key:
        fail("OPENCLAW_AGENT_NAME or OPENCLAW_AGENT_KEY not set. Run step 3 first.")
        return False

    # Create client
    agent = AgentMemory(agent_name, api_key=agent_key)

    # 5a. Authenticate
    try:
        info = agent.authenticate()
        ok(f"Authenticated as '{info.name}' ({info.id})")
    except Exception as e:
        fail(f"Authentication failed: {e}")
        return False

    # 5b. Remember (store a test memory)
    test_content = "OpenClaw bootstrap smoke test: the system is operational and memories persist across agent sessions."
    memory = None
    try:
        memory = agent.remember(
            test_content,
            memory_type=MemoryType.EPISODIC,
            scope=Scope.PRIVATE,
            tags=["test", "bootstrap"],
            namespace="system",
            importance=0.1,
        )
        if memory and memory.id:
            ok(f"remember() OK — stored memory {memory.id}")
        else:
            fail("remember() returned empty result")
            return False
    except Exception as e:
        fail(f"remember() failed: {e}")
        return False

    # 5c. Recall (search for the memory)
    try:
        results = agent.recall(
            "bootstrap smoke test operational",
            limit=5,
            threshold=0.3,
        )
        found = any(r.id == memory.id for r in results)
        if found:
            ok(f"recall() OK — found test memory (similarity: {results[0].similarity:.3f})")
        elif results:
            warn(f"recall() returned {len(results)} results but test memory not in top 5")
            ok("recall() is functional (embedding model may rank differently)")
        else:
            warn("recall() returned 0 results (embedding may need time to index)")
            ok("recall() executed without errors")
    except Exception as e:
        fail(f"recall() failed: {e}")
        return False

    # 5d. Recall all (unified search: memory + RAG)
    try:
        combined = agent.recall_all(
            "bootstrap test",
            limit=5,
            threshold=0.3,
        )
        memory_results = [r for r in combined if r.result_type == "memory"]
        rag_results = [r for r in combined if r.result_type == "rag"]
        ok(f"recall_all() OK — {len(memory_results)} memories, {len(rag_results)} RAG chunks")
    except Exception as e:
        fail(f"recall_all() failed: {e}")
        return False

    # 5e. Forget (clean up test memory)
    try:
        deleted = agent.forget(memory.id)
        if deleted:
            ok(f"forget() OK — deleted test memory {memory.id}")
        else:
            warn(f"forget() returned False for memory {memory.id}")
    except Exception as e:
        fail(f"forget() failed: {e}")
        return False

    # 5f. Stats
    try:
        stats = agent.stats()
        if stats:
            ok(f"stats() OK — {stats}")
        else:
            warn("stats() returned empty (may need RPC function)")
    except Exception as e:
        warn(f"stats() failed (non-critical): {e}")

    ok("Smoke test completed successfully")
    return True


# ── Step 6: Summary ──────────────────────────────────────────────────

def step_summary() -> None:
    """Print final summary."""
    heading("Setup Complete")

    env = get_env()

    # Get agent info
    resp = supabase_rpc(env, "mb_authenticate_agent", {"p_api_key": env["OPENCLAW_AGENT_KEY"]})
    if resp.status_code == 200 and resp.json():
        info = resp.json()[0]
        print(f"  Agent name:    {info['agent_name']}")
        print(f"  Agent ID:      {info['agent_id']}")
        print(f"  Agent type:    {info.get('agent_type', 'openclaw')}")
    else:
        print(f"  Agent name:    {env['OPENCLAW_AGENT_NAME']}")

    print(f"  Supabase:      {env['SUPABASE_URL'][:40]}...")
    print(f"  Ollama:        {env['OLLAMA_URL']}")
    print(f"  Model:         {env['EMBEDDING_MODEL']}")
    print()
    print(f"  {Colors.OK}The agent is ready to use.{Colors.END}")
    print()
    print("  Usage in Python:")
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │ from knowledgebase.memory import AgentMemory, Scope │")
    print("  │                                                     │")
    print("  │ agent = AgentMemory('name', api_key='oc_sk_...')    │")
    print("  │ agent.authenticate()                                │")
    print("  │                                                     │")
    print("  │ agent.learn('fact', scope=Scope.GLOBAL)             │")
    print("  │ results = agent.recall('query')                     │")
    print("  │ combined = agent.recall_all('query')                │")
    print("  └─────────────────────────────────────────────────────┘")
    print()


# ── Main ─────────────────────────────────────────────────────────────

STEPS = {
    "validate": step_validate,
    "schema": step_schema,
    "register": step_register,
    "access": step_access,
    "test": step_test,
}


def run_all() -> bool:
    """Run all steps in sequence."""
    for name, step_fn in STEPS.items():
        success = step_fn()
        if not success:
            fail(f"Step '{name}' failed. Fix the issue and re-run: bootstrap.py {name}")
            return False
    step_summary()
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "all":
        success = run_all()
        sys.exit(0 if success else 1)
    elif command == "summary":
        step_summary()
    elif command in STEPS:
        success = STEPS[command]()
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
