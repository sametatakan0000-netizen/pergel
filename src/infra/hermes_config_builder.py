"""Hermes Agent resmi şemasına uygun tam potansiyel konfigürasyon, Custom Oracle Router Proxy ve Nous Portal entegrasyonu."""
from typing import Any, Dict, List


def build_optimal_hermes_spec() -> Dict[str, Any]:
    """Resmî Hermes Agent dokümantasyonu ve canlı Nous Portal (57+ model kataloğu) ile doğrulanmış şema."""
    return {
        "model": {
            "provider": "nous",
            "default": "google/gemini-4-argon",
            "switch_context_confirm_tokens": 100000,
        },
        "nous": {
            "anthropic_wire": "chat",
            "keepalive_interval_seconds": 900,
        },
        "subscription_proxy": {
            "enabled": True,
            "upstream_url": "http://127.0.0.1:8645/v1",
            "provider": "nous",
        },
        "providers": {
            "oracle-router": {
                "api": "http://127.0.0.1:8090/v1",
                "transport": "chat_completions",
                "session_affinity_header": "x-hermes-session-id",
                "catalog_provider": "nous",
                "default_model": "oracle/auto",
                "models": {
                    "oracle/auto": {},
                },
            }
        },
        "agent": {
            "max_turns": 90,
            "reasoning_effort": "medium",
            "tool_use_enforcement": True,
            "verify_on_stop": True,
        },
        "terminal": {
            "backend": "docker",
            "timeout": 180,
        },
        "checkpoints": {
            "enabled": True,
            "max_snapshots": 50,
        },
        "compression": {
            "enabled": True,
            "threshold": 0.50,
            "target_ratio": 0.20,
        },
        "delegation": {
            "max_concurrent_children": 10,
            "max_iterations": 50,
            "max_spawn_depth": 2,
        },
        "approvals": {
            "mode": "smart",
            "timeout": 60,
        },
        "security": {
            "redact_secrets": True,
        },
        "curator": {
            "enabled": True,
            "consolidate": False,
            "interval_hours": 24,
            "stale_after_days": 14,
        },
        "web": {
            "search_provider": "searxng",
            "extract_provider": "firecrawl",
            "extract_char_limit": 25000,
            "extract_timeout": 120,
            "cache_enabled": True,
            "cache_ttl_minutes": 20,
        },
        "browser": {
            "backend": "browser-use",
            "inactivity_timeout": 300,
            "command_timeout": 60,
            "auto_local_for_private_urls": True,
        },
        "auxiliary": {
            "vision": {"provider": "nous", "model": "google/gemini-4-argon"},
            "compression": {"provider": "nous", "model": "upstage/solar-mini4"},
            "web_extract": {"provider": "nous", "model": "upstage/solar-mini4"},
            "title_generation": {"provider": "nous", "model": "upstage/solar-mini4"},
            "approval": {"provider": "nous", "model": "qwen/qwen3.8-27b"},
            "skills_hub": {"provider": "nous", "model": "deepseek/deepseek-v4.1-flash-1017"},
            "kanban_decomposer": {"provider": "nous", "model": "deepseek/deepseek-v4-pro"},
            "mcp": {"provider": "nous", "model": "z-ai/glm-5.2"},
            "curator": {"provider": "nous", "model": "openai/gpt-6.1-sol"},
            "triage_specifier": {"provider": "nous", "model": "qwen/qwen3.8-27b"},
            "profile_describer": {"provider": "nous", "model": "qwen/qwen3.8-27b"},
        },
        "moa": {
            "default_preset": "default",
            "privacy_filter": "display",
            "presets": {
                "default": {
                    "enabled": True,
                    "fanout": "every_n:3",
                    "reference_models": [
                        {
                            "provider": "nous",
                            "model": "deepseek/deepseek-v4-pro",
                            "reasoning_effort": "medium",
                        },
                        {
                            "provider": "nous",
                            "model": "openai/gpt-6.1-sol",
                            "reasoning_effort": "medium",
                        },
                        {
                            "provider": "nous",
                            "model": "qwen/qwen3.8-27b",
                            "reasoning_effort": "low",
                        },
                    ],
                    "aggregator": {
                        "provider": "nous",
                        "model": "google/gemini-4-argon",
                        "reasoning_effort": "high",
                    },
                }
            },
        },
    }


def generate_hermes_cli_commands(spec: Dict[str, Any]) -> List[str]:
    """Preview only: register a named endpoint without switching the live main model."""
    provider = spec["providers"]["oracle-router"]
    return [
        "# PREVIEW ONLY. Run on the Hermes HOST after both services are healthy.",
        "# Does not start services, alter the main model, or install skills.",
        f"hermes config set providers.oracle-router.api {provider['api']}",
        f"hermes config set providers.oracle-router.transport {provider['transport']}",
        f"hermes config set providers.oracle-router.session_affinity_header {provider['session_affinity_header']}",
        f"hermes config set providers.oracle-router.catalog_provider {provider['catalog_provider']}",
        f"hermes config set providers.oracle-router.default_model {provider['default_model']}",
    ]
