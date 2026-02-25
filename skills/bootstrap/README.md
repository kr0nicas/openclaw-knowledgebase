# bootstrap

Sets up an OpenClaw agent with shared memory on Supabase.

## What it does

1. Validates environment (Supabase, Ollama connections)
2. Applies database schema (RAG tables + memory tables)
3. Registers this agent with a unique API key
4. Grants access to existing RAG knowledge bases
5. Runs an end-to-end smoke test
6. Reports status

## Quick start

```bash
python3 skills/bootstrap/bootstrap.py all
```

## For agents

Read `instructions.md` for step-by-step guidance.
