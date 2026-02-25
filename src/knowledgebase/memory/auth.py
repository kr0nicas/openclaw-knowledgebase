"""API key generation and hashing for agent authentication.

Agent API keys follow the format: mb_sk_<random>
Hashing is done server-side via pgcrypto's crypt()/gen_salt('bf').
This module only generates the raw key; the SQL function handles hashing.
"""

import secrets


def generate_api_key(prefix: str = "oc") -> str:
    """Generate a new agent API key.

    Returns a key like 'oc_sk_abc123...' (51 chars total).
    The key should be shown to the user once, then only the bcrypt hash
    is stored in mb_agents.api_key_hash via mb_register_agent().
    """
    token = secrets.token_urlsafe(32)
    return f"{prefix}_sk_{token}"
