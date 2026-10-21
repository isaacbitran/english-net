#!/bin/sh
# Prompt Guard 2 86M is gated. Accept Meta's license at https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M,
# then run:  HF_TOKEN=hf_... sh scripts/run_promptguard2.sh
set -e
cd "$(dirname "$0")/.."
: "${HF_TOKEN:?set HF_TOKEN to a Hugging Face token that has accepted the license}"
HF_TOKEN="$HF_TOKEN" .venv/bin/python -m englishnet.baselines score --models promptguard2
.venv/bin/python -m englishnet.baselines table
