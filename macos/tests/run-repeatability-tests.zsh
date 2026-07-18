#!/bin/zsh

set -eu

script_directory=$(cd -- "$(dirname -- "$0")" && pwd)
macos_directory=$(cd -- "$script_directory/.." && pwd)
repo_root=$(cd -- "$macos_directory/.." && pwd)
manager="$macos_directory/manage-finder-quick-action.sh"
runtime_directory="$HOME/Library/Application Support/QuickTunnelReviewShare"
workflow_path="$HOME/Library/Services/Share to Codex Review.workflow"
workflow_template="$macos_directory/templates/Share to Codex Review.workflow"
skip_confirmation=0

if [[ ${1:-} == "--yes" ]]; then
    skip_confirmation=1
elif [[ $# -ne 0 ]]; then
    print -u2 "Usage: $0 [--yes]"
    exit 64
fi

if [[ -e "$runtime_directory" || -e "$workflow_path" ]]; then
    print -u2 "ERROR: An existing or partial Quick Tunnel installation is present."
    print -u2 "Preserve or uninstall it before running the repeatability test."
    exit 73
fi

if [[ $skip_confirmation -ne 1 ]]; then
    print "This performs two install/status/uninstall cycles in your user Library."
    print "Removed test installations remain recoverable in sibling .del folders."
    read "answer?Type REPEAT to continue: "
    if [[ "$answer" != "REPEAT" ]]; then
        print "Repeatability test cancelled. No files were changed."
        exit 0
    fi
fi

cleanup_partial_installation() {
    if [[ -e "$runtime_directory" || -e "$workflow_path" ]]; then
        "$manager" uninstall --yes >/dev/null 2>&1 || true
    fi
}

trap cleanup_partial_installation EXIT

assert_same_file() {
    source_path=$1
    installed_path=$2
    if ! /usr/bin/cmp -s -- "$source_path" "$installed_path"; then
        print -u2 "ERROR: Installed bytes differ: $installed_path"
        return 1
    fi
}

"$manager" doctor

python_path=$(command -v python3)
PYTHONDONTWRITEBYTECODE=1 "$python_path" -m unittest discover \
    -s "$script_directory" -v

for shell_file in \
    "$macos_directory/share-codex-review.command" \
    "$macos_directory/launch-from-finder.sh" \
    "$macos_directory/manage-finder-quick-action.sh" \
    "$macos_directory/finder-quick-action-setup.command" \
    "$script_directory/run-repeatability-tests.zsh"
do
    /bin/zsh -n "$shell_file"
done

for cycle in 1 2; do
    print "Repeatability cycle $cycle: install"
    "$manager" install --yes
    "$manager" status

    pbs_path="/System/Library/CoreServices/pbs"
    if [[ -x "$pbs_path" ]] \
        && ! "$pbs_path" -dump 2>/dev/null \
            | /usr/bin/grep -Fq "NSBundlePath = \"$workflow_path\";"
    then
        print -u2 "ERROR: Cycle $cycle was not registered in Finder Services."
        exit 1
    fi

    assert_same_file \
        "$macos_directory/share-codex-review.py" \
        "$runtime_directory/share-codex-review.py"
    assert_same_file \
        "$macos_directory/share-codex-review.command" \
        "$runtime_directory/share-codex-review.command"
    assert_same_file \
        "$macos_directory/launch-from-finder.sh" \
        "$runtime_directory/launch-from-finder.sh"
    assert_same_file \
        "$repo_root/safe-review-server.py" \
        "$runtime_directory/safe-review-server.py"
    assert_same_file \
        "$workflow_template/Contents/Info.plist" \
        "$workflow_path/Contents/Info.plist"
    assert_same_file \
        "$workflow_template/Contents/document.wflow" \
        "$workflow_path/Contents/document.wflow"

    print "Repeatability cycle $cycle: uninstall"
    "$manager" uninstall --yes
    if "$manager" status >/dev/null 2>&1; then
        print -u2 "ERROR: Cycle $cycle left an active Finder integration."
        exit 1
    fi
done

trap - EXIT
print "Repeatability verification: Passed (2 identical install cycles)"
