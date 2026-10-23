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
                    "oracle/auto": {
                        "context_length": 1000000,
                        "supports_vision": True,
                        "prompt_caching": True,
                    },
                    "oracle/eco": {
                        "context_length": 256000,
                        "supports_vision": True,
                        "prompt_caching": True,
                    },
                    "oracle/free": {
                        "context_length": 128000,
                        "supports_vision": False,
                        "prompt_caching": False,
                    },
                },
            }
        },
        "smart_model_routing": {
            "enabled": True,
            "max_simple_chars": 160,
            "max_simple_words": 28,
            "cheap_model": {
                "provider": "nous",
                "model": "qwen/qwen3.8-27b",
            },
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
    """Hard Invariant uyumlu (`hermes config set` + `hermes proxy start`) komut listesi üretir."""
    cmds = [
        "# 1. Nous Portal Subscription Proxy'yi başlat (:8645 -> OAuth otomatik JWT yenileme)",
        "hermes proxy start --host 127.0.0.1 --port 8645 &",
        "# 2. Named Custom Provider olarak yerel Self-Evolving Oracle Router Proxy (:8090) tanımla",
        f"hermes config set providers.oracle-router.api {spec['providers']['oracle-router']['api']}",
        f"hermes config set providers.oracle-router.transport {spec['providers']['oracle-router']['transport']}",
        f"hermes config set providers.oracle-router.session_affinity_header {spec['providers']['oracle-router']['session_affinity_header']}",
        f"hermes config set providers.oracle-router.catalog_provider {spec['providers']['oracle-router']['catalog_provider']}",
        f"hermes config set providers.oracle-router.default_model {spec['providers']['oracle-router']['default_model']}",
        "# 3. Ana model ve Nous Portal wire optimizasyonu (Prompt Cache korunumu için anthropic_wire=chat)",
        f"hermes config set model.provider {spec['model']['provider']}",
        f"hermes config set model.default {spec['model']['default']}",
        f"hermes config set model.switch_context_confirm_tokens {spec['model']['switch_context_confirm_tokens']}",
        f"hermes config set nous.anthropic_wire {spec['nous']['anthropic_wire']}",
        f"hermes config set smart_model_routing.enabled {str(spec['smart_model_routing']['enabled']).lower()}",
        f"hermes config set smart_model_routing.cheap_model.provider {spec['smart_model_routing']['cheap_model']['provider']}",
        f"hermes config set smart_model_routing.cheap_model.model {spec['smart_model_routing']['cheap_model']['model']}",
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
