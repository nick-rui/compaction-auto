#!/bin/bash
# Transcripts from safety-research/assistant-axis (Lu et al. 2026) used as on-policy drifted histories.
set -e
cd "$(dirname "$0")"
tmp=$(mktemp -d)
git clone -q --depth 1 https://github.com/safety-research/assistant-axis.git "$tmp/aa"
mkdir -p data
cp "$tmp"/aa/transcripts/case_studies/qwen-3-32b/*.json "$tmp"/aa/transcripts/persona_drift/*.json data/
rm -rf "$tmp"
