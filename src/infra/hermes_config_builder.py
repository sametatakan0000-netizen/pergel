"""Hermes Agent resmi şemasına uygun tam potansiyel konfigürasyon ve CLI komut üreticisi."""
from typing import Any, Dict, List


def build_optimal_hermes_spec() -> Dict[str, Any]:
    """Resmî Hermes Agent dokümantasyonuyla doğrulanmış tam potansiyel ayar şeması."""
    return {
        "model": {
            "provider": "nous",
            "default": "google/gemini-4-argon",
            "switch_context_confirm_tokens": 100000,
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
            "compression": {"provider": "nous", "model": "google/gemini-3.7-flash:free"},
            "web_extract": {"provider": "nous", "model": "google/gemini-3.7-flash:free"},
            "title_generation": {"provider": "nous", "model": "google/gemini-3.7-flash:free"},
            "approval": {"provider": "nous", "model": "google/gemini-3.7-flash:free"},
            "skills_hub": {"provider": "nous", "model": "deepseek/deepseek-v4-pro"},
            "kanban_decomposer": {"provider": "nous", "model": "deepseek/deepseek-v4-pro"},
            "mcp": {"provider": "nous", "model": "openai/gpt-6-sol"},
            "curator": {"provider": "nous", "model": "openai/gpt-6-sol"},
            "triage_specifier": {"provider": "nous", "model": "qwen/qwen3.6-27b"},
            "profile_describer": {"provider": "nous", "model": "qwen/qwen3.6-27b"},
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
                            "model": "openai/gpt-6-sol",
                            "reasoning_effort": "medium",
                        },
                        {
                            "provider": "nous",
                            "model": "qwen/qwen3.6-27b",
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
    """Hard Invariant uyumlu (`hermes config set`) komut listesi üretir."""
    cmds = [
        f"hermes config set model.provider {spec['model']['provider']}",
        f"hermes config set model.default {spec['model']['default']}",
        f"hermes config set model.switch_context_confirm_tokens {spec['model']['switch_context_confirm_tokens']}",
        f"hermes config set terminal.backend {spec['terminal']['backend']}",
        f"hermes config set checkpoints.enabled {str(spec['checkpoints']['enabled']).lower()}",
        f"hermes config set checkpoints.max_snapshots {spec['checkpoints']['max_snapshots']}",
        f"hermes config set delegation.max_concurrent_children {spec['delegation']['max_concurrent_children']}",
        f"hermes config set delegation.max_iterations {spec['delegation']['max_iterations']}",
        f"hermes config set delegation.max_spawn_depth {spec['delegation']['max_spawn_depth']}",
        f"hermes config set approvals.mode {spec['approvals']['mode']}",
        f"hermes config set security.redact_secrets {str(spec['security']['redact_secrets']).lower()}",
        f"hermes config set moa.privacy_filter {spec['moa']['privacy_filter']}",
        f"hermes config set web.extract_char_limit {spec['web']['extract_char_limit']}",
        f"hermes config set web.cache_ttl_minutes {spec['web']['cache_ttl_minutes']}",
        "hermes config set SEARXNG_URL http://localhost:8888",
        "hermes config set FIRECRAWL_API_URL http://localhost:3002",
        "hermes skills tap add morluto/rea",
        "hermes skills tap add vercel-labs/agent-skills",
        "hermes skills install official/research/searxng-search",
    ]
    for task, cfg in spec["auxiliary"].items():
        cmds.append(f"hermes config set auxiliary.{task}.provider {cfg['provider']}")
        cmds.append(f"hermes config set auxiliary.{task}.model {cfg['model']}")
    return cmds
