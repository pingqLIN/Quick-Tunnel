#!/bin/zsh

set -u

script_directory=$(cd -- "$(dirname -- "$0")" && pwd)
python_path=$(command -v python3 || true)

if [[ -z "$python_path" ]]; then
    print -u2 "ERROR: Python 3.9 or newer was not found. Install it and retry."
    read "acknowledgement?Press RETURN to close this window"
    exit 1
fi

if ! "$python_path" -c \
    'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'
then
    print -u2 "ERROR: Python 3.9 or newer is required."
    read "acknowledgement?Press RETURN to close this window"
    exit 1
fi

if [[ $# -eq 0 ]]; then
    read "target_folder?Folder to share: "
    if [[ -z "$target_folder" ]]; then
        print "No folder selected."
        exit 0
    fi
    set -- "$target_folder"
fi

exec "$python_path" \
    "$script_directory/share-codex-review.py" \
    "$@" \
    --wait-for-acknowledgement
