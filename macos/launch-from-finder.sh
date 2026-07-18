#!/bin/zsh

set -u

script_directory=$(cd -- "$(dirname -- "$0")" && pwd)
runner_path="$script_directory/share-codex-review.command"

show_error() {
    /usr/bin/osascript -e "display alert \"Quick Tunnel Review Share\" message \"$1\" as warning"
}

if [[ $# -ne 1 ]]; then
    show_error "Select exactly one folder in Finder, then run the Quick Action again."
    exit 64
fi

selected_folder=$1
if [[ ! -d "$selected_folder" ]]; then
    show_error "The selected Finder item is not a folder."
    exit 66
fi

if [[ ! -x "$runner_path" ]]; then
    show_error "The Quick Tunnel runtime is incomplete. Reinstall the Finder Quick Action."
    exit 69
fi

/usr/bin/osascript - "$runner_path" "$selected_folder" <<'APPLESCRIPT'
on run argv
    set runnerPath to item 1 of argv
    set folderPath to item 2 of argv
    set commandText to quoted form of runnerPath & space & quoted form of folderPath

    tell application "Terminal"
        activate
        do script commandText
    end tell
end run
APPLESCRIPT
