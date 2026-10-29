#!/bin/bash

set -euo pipefail

run_if_found() {
    local cmd="$1"
    shift
    if command -v "$cmd" >/dev/null 2>&1; then
        "$cmd" "$@"
    fi
}


destination="$HOME/.bash_completion"
temporary=$(mktemp "${destination}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT

run_if_found poetry completions bash >> "$temporary"
run_if_found ruff generate-shell-completion bash >> "$temporary"
if command -v git-lfs >/dev/null 2>&1; then
    git-lfs completion bash >> "$temporary"
fi
run_if_found uv generate-shell-completion bash >> "$temporary"
run_if_found pip completion --bash >> "$temporary"

mv -- "$temporary" "$destination"
