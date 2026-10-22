#!/usr/bin/env bash
set -euo pipefail

# Hermes Agent Tam Potansiyel Konfigürasyon Mühürleme Betiği (Ubuntu Host üzerinde çalıştırılır)
PYTHONPATH="/root/ai_browser_farm" python3 -c '
from src.infra.hermes_config_builder import build_optimal_hermes_spec, generate_hermes_cli_commands
for cmd in generate_hermes_cli_commands(build_optimal_hermes_spec()):
    print(cmd)
'
