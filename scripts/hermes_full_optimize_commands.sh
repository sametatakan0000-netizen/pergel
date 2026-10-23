#!/usr/bin/env bash
set -euo pipefail
# 1. Nous Portal Subscription Proxy'yi başlat (:8645 -> OAuth otomatik JWT yenileme)
hermes proxy start --host 127.0.0.1 --port 8645 &
# 2. Named Custom Provider olarak yerel Self-Evolving Oracle Router Proxy (:8090) tanımla
hermes config set providers.oracle-router.api http://127.0.0.1:8090/v1
hermes config set providers.oracle-router.transport chat_completions
hermes config set providers.oracle-router.session_affinity_header x-hermes-session-id
hermes config set providers.oracle-router.catalog_provider nous
hermes config set providers.oracle-router.default_model oracle/auto
# 3. Ana model ve Nous Portal wire optimizasyonu (Prompt Cache korunumu için anthropic_wire=chat)
hermes config set model.provider nous
hermes config set model.default google/gemini-4-argon
hermes config set model.switch_context_confirm_tokens 100000
hermes config set nous.anthropic_wire chat
hermes config set smart_model_routing.enabled true
hermes config set smart_model_routing.cheap_model.provider nous
hermes config set smart_model_routing.cheap_model.model qwen/qwen3.8-27b
hermes config set terminal.backend docker
hermes config set checkpoints.enabled true
hermes config set checkpoints.max_snapshots 50
hermes config set delegation.max_concurrent_children 10
hermes config set delegation.max_iterations 50
hermes config set delegation.max_spawn_depth 2
hermes config set approvals.mode smart
hermes config set security.redact_secrets true
hermes config set moa.privacy_filter display
hermes config set web.extract_char_limit 25000
hermes config set web.cache_ttl_minutes 20
hermes config set SEARXNG_URL http://localhost:8888
hermes config set FIRECRAWL_API_URL http://localhost:3002
hermes skills tap add morluto/rea
hermes skills tap add vercel-labs/agent-skills
hermes skills install official/research/searxng-search
hermes config set auxiliary.vision.provider nous
hermes config set auxiliary.vision.model google/gemini-4-argon
hermes config set auxiliary.compression.provider nous
hermes config set auxiliary.compression.model upstage/solar-mini4
hermes config set auxiliary.web_extract.provider nous
hermes config set auxiliary.web_extract.model upstage/solar-mini4
hermes config set auxiliary.title_generation.provider nous
hermes config set auxiliary.title_generation.model upstage/solar-mini4
hermes config set auxiliary.approval.provider nous
hermes config set auxiliary.approval.model qwen/qwen3.8-27b
hermes config set auxiliary.skills_hub.provider nous
hermes config set auxiliary.skills_hub.model deepseek/deepseek-v4.1-flash-1017
hermes config set auxiliary.kanban_decomposer.provider nous
hermes config set auxiliary.kanban_decomposer.model deepseek/deepseek-v4-pro
hermes config set auxiliary.mcp.provider nous
hermes config set auxiliary.mcp.model z-ai/glm-5.2
hermes config set auxiliary.curator.provider nous
hermes config set auxiliary.curator.model openai/gpt-6.1-sol
hermes config set auxiliary.triage_specifier.provider nous
hermes config set auxiliary.triage_specifier.model qwen/qwen3.8-27b
hermes config set auxiliary.profile_describer.provider nous
hermes config set auxiliary.profile_describer.model qwen/qwen3.8-27b
