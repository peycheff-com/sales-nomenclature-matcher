"""Dynamic AI Gateway settings

Revision ID: ede63bcb39f8
Revises: 0004_must_change_password
Create Date: 2026-04-01 14:02:54.321040

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ede63bcb39f8'
down_revision: Union[str, Sequence[str], None] = '0004_must_change_password'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: move individual API keys to a providers_registry JSON."""
    conn = op.get_bind()
    
    # Read existing keys
    res = conn.execute(sa.text("SELECT key, value FROM system_settings"))
    current_settings = {row[0]: row[1] for row in res}
    
    providers = {
        "local": {
            "id": "local",
            "name": "Local Pipeline (OSS)",
            "api_key": "none",
            "base_url": "http://localhost:11434/v1"
        }
    }
    
    # Build provider configs from existing keys
    if "openai_api_key" in current_settings and current_settings["openai_api_key"]:
        providers["openai"] = {
            "id": "openai",
            "name": "OpenAI",
            "api_key": current_settings["openai_api_key"],
            "base_url": "https://api.openai.com/v1"
        }
    if "openrouter_api_key" in current_settings and current_settings["openrouter_api_key"]:
        providers["openrouter"] = {
            "id": "openrouter",
            "name": "OpenRouter",
            "api_key": current_settings["openrouter_api_key"],
            "base_url": "https://openrouter.ai/api/v1"
        }
    if "google_api_key" in current_settings and current_settings["google_api_key"]:
        providers["google"] = {
            "id": "google",
            "name": "Google Gemini",
            "api_key": current_settings["google_api_key"],
            "base_url": ""
        }
    if "cohere_api_key" in current_settings and current_settings["cohere_api_key"]:
        providers["cohere"] = {
            "id": "cohere",
            "name": "Cohere",
            "api_key": current_settings["cohere_api_key"],
            "base_url": "https://api.cohere.ai/v1"
        }
        
    # Save the registry
    conn.execute(
        sa.text("""
            INSERT INTO system_settings (key, value, updated_at) 
            VALUES (:key, :value, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """),
        {"key": "providers_registry", "value": json.dumps(providers)}
    )

    # Delete old keys
    old_keys = ["openai_api_key", "openrouter_api_key", "google_api_key", "cohere_api_key",
                "openai_base_url", "openrouter_base_url"]
    conn.execute(
        sa.text("DELETE FROM system_settings WHERE key = ANY(:keys)"),
        {"keys": old_keys}
    )


def downgrade() -> None:
    """Downgrade schema: move providers_registry back to individual keys."""
    conn = op.get_bind()
    res = conn.execute(sa.text("SELECT value FROM system_settings WHERE key = 'providers_registry'"))
    row = res.fetchone()
    if row:
        try:
            providers = json.loads(row[0])
            for key, config in providers.items():
                if key == "openai":
                    conn.execute(sa.text("INSERT INTO system_settings (key, value, updated_at) VALUES ('openai_api_key', :v, NOW()) ON CONFLICT (key) DO NOTHING"), {"v": config.get("api_key", "")})
                elif key == "openrouter":
                    conn.execute(sa.text("INSERT INTO system_settings (key, value, updated_at) VALUES ('openrouter_api_key', :v, NOW()) ON CONFLICT (key) DO NOTHING"), {"v": config.get("api_key", "")})
                elif key == "google":
                    conn.execute(sa.text("INSERT INTO system_settings (key, value, updated_at) VALUES ('google_api_key', :v, NOW()) ON CONFLICT (key) DO NOTHING"), {"v": config.get("api_key", "")})
                elif key == "cohere":
                    conn.execute(sa.text("INSERT INTO system_settings (key, value, updated_at) VALUES ('cohere_api_key', :v, NOW()) ON CONFLICT (key) DO NOTHING"), {"v": config.get("api_key", "")})
        except Exception:
            pass
            
    conn.execute(sa.text("DELETE FROM system_settings WHERE key = 'providers_registry'"))

