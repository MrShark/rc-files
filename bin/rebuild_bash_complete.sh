#!/bin/bash

set -euo pipefail

run_if_found() {
    local cmd="$1"
    shift
    if command -v "$cmd" >/dev/null 2>&1; then
        "$cmd" "$@"
    fi
}


> ~/.bash_completion

run_if_found poetry completions bash >> ~/.bash_completion
run_if_found ruff generate-shell-completion bash >> ~/.bash_completion
run_if_found git lfs completion bash  >> ~/.bash_completion
