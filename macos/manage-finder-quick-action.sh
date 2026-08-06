#!/bin/zsh

set -u

script_directory=$(cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(cd -- "$script_directory/.." && pwd)
runtime_directory="$HOME/Library/Application Support/QuickTunnelReviewShare"
services_directory="$HOME/Library/Services"
workflow_path="$services_directory/Share to Codex Review.workflow"
workflow_template="$script_directory/templates/Share to Codex Review.workflow"
safe_server_source="$repo_root/safe-review-server.py"
pbs_path="/System/Library/CoreServices/pbs"
stage_root=""
skip_confirmation=0

usage() {
    print "Usage: $0 <doctor|install|uninstall|status> [--yes]"
}

cleanup_stage() {
    if [[ -n "$stage_root" && -d "$stage_root" ]]; then
        case "$stage_root" in
            /tmp/quick-tunnel-install.*)
                move_to_del "$stage_root"
                ;;
        esac
    fi
}

trap cleanup_stage EXIT

move_to_del() {
    target_path=$1
    if [[ ! -e "$target_path" ]]; then
        return
    fi

    parent_directory=$(dirname -- "$target_path")
    base_name=$(basename -- "$target_path")
    del_directory="$parent_directory/.del"
    timestamp=$(/bin/date +%Y%m%d-%H%M%S)
    destination_path="$del_directory/$base_name-$timestamp"
    collision_suffix=1

    /bin/mkdir -p -- "$del_directory"
    while [[ -e "$destination_path" ]]; do
        destination_path="$del_directory/$base_name-$timestamp-$collision_suffix"
        collision_suffix=$((collision_suffix + 1))
    done

    /bin/mv -- "$target_path" "$destination_path"
    print "Moved existing path to: $destination_path"
}

confirm_action() {
    expected_word=$1
    prompt=$2
    if [[ $skip_confirmation -eq 1 ]]; then
        return 0
    fi

    print "$prompt"
    read "answer?Type $expected_word to continue: "
    [[ "$answer" == "$expected_word" ]]
}

refresh_services() {
    if [[ ! -x "$pbs_path" ]]; then
        print -u2 "NOTICE: macOS Services registry verification is unavailable; Finder will discover the installed workflow."
        return 0
    fi

    if ! "$pbs_path" -update >/dev/null 2>&1; then
        print -u2 "NOTICE: Finder Services registration refresh was not confirmed; Finder may discover the workflow asynchronously."
        return 0
    fi
}

is_service_registered() {
    [[ -x "$pbs_path" ]] || return 1
    "$pbs_path" -dump 2>/dev/null \
        | /usr/bin/grep -Fq \
            "NSBundlePath = \"$workflow_path\";"
}

find_supported_python() {
    python_path=$(command -v python3 || true)
    if [[ -z "$python_path" ]]; then
        print -u2 "ERROR: Python 3.9 or newer is required."
        return 1
    fi

    if ! "$python_path" - <<'PYTHON'
import sys

raise SystemExit(0 if sys.version_info >= (3, 9) else 1)
PYTHON
    then
        python_version=$(
            "$python_path" -c 'import platform; print(platform.python_version())' \
                2>/dev/null || print unknown
        )
        print -u2 "ERROR: Python 3.9 or newer is required; found $python_version."
        return 1
    fi
}

doctor_action() {
    if [[ $(uname -s) != "Darwin" ]]; then
        print -u2 "ERROR: The macOS compatibility check requires macOS."
        return 1
    fi

    for required_tool in /bin/zsh /usr/bin/plutil; do
        if [[ ! -x "$required_tool" ]]; then
            print -u2 "ERROR: Required macOS tool is unavailable: $required_tool"
            return 1
        fi
    done

    if ! find_supported_python; then
        return 1
    fi

    cloudflared_path=$(command -v cloudflared || true)
    if [[ -z "$cloudflared_path" ]]; then
        print -u2 "ERROR: cloudflared is required and was not found in PATH."
        return 1
    fi
    cloudflared_version=$($cloudflared_path --version 2>&1) || {
        print -u2 "ERROR: cloudflared was found but its version could not be read."
        return 1
    }

    for source_file in \
        "$script_directory/share-codex-review.py" \
        "$script_directory/share-codex-review.command" \
        "$script_directory/launch-from-finder.sh" \
        "$safe_server_source" \
        "$workflow_template/Contents/Info.plist" \
        "$workflow_template/Contents/document.wflow"
    do
        if [[ ! -f "$source_file" ]]; then
            print -u2 "ERROR: Required source file is missing: $source_file"
            return 1
        fi
    done

    if ! "$python_path" - "$script_directory/share-codex-review.py" <<'PYTHON'
import ast
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
PYTHON
    then
        print -u2 "ERROR: The macOS Python entry point failed validation."
        return 1
    fi

    /usr/bin/plutil -lint "$workflow_template/Contents/Info.plist" >/dev/null \
        || return 1
    /usr/bin/plutil -lint "$workflow_template/Contents/document.wflow" >/dev/null \
        || return 1

    print "Compatibility check: Passed"
    print "Python: $($python_path -c 'import platform; print(platform.python_version())')"
    print "cloudflared: $cloudflared_version"
    qrencode_path=$(command -v qrencode || true)
    if [[ -n "$qrencode_path" ]]; then
        print "qrencode: Available ($($qrencode_path --version 2>&1 | /usr/bin/head -n 1))"
    else
        print "qrencode: Unavailable (optional)"
    fi
    if [[ -x "$pbs_path" ]]; then
        print "Finder Services registry verification: Available"
    else
        print "Finder Services registry verification: Unavailable (non-blocking)"
    fi
}

show_status() {
    missing_count=0
    for required_file in \
        "$runtime_directory/share-codex-review.py" \
        "$runtime_directory/share-codex-review.command" \
        "$runtime_directory/launch-from-finder.sh" \
        "$runtime_directory/safe-review-server.py" \
        "$workflow_path/Contents/Info.plist" \
        "$workflow_path/Contents/document.wflow"
    do
        if [[ ! -f "$required_file" ]]; then
            missing_count=$((missing_count + 1))
        fi
    done

    if [[ $missing_count -eq 0 ]] \
        && /usr/bin/grep -q "QuickTunnelReviewShare/launch-from-finder.sh" \
            "$workflow_path/Contents/document.wflow"
    then
        print "Finder Quick Action: Installed"
        print "Runtime: $runtime_directory"
        print "Workflow: $workflow_path"
        if is_service_registered; then
            print "Registry verification: Verified"
        elif [[ -x "$pbs_path" ]]; then
            print "Registry verification: Not confirmed; Finder may discover the workflow asynchronously"
        else
            print "Registry verification: Unavailable on this macOS version"
        fi
        return 0
    fi

    if [[ -e "$runtime_directory" || -e "$workflow_path" ]]; then
        print "Finder Quick Action: Drift detected or incomplete"
        return 1
    fi

    print "Finder Quick Action: Not installed"
    return 1
}

install_action() {
    if [[ $(uname -s) != "Darwin" ]]; then
        print -u2 "ERROR: Finder Quick Action installation requires macOS."
        return 1
    fi

    for source_file in \
        "$script_directory/share-codex-review.py" \
        "$script_directory/share-codex-review.command" \
        "$script_directory/launch-from-finder.sh" \
        "$safe_server_source" \
        "$workflow_template/Contents/Info.plist" \
        "$workflow_template/Contents/document.wflow"
    do
        if [[ ! -f "$source_file" ]]; then
            print -u2 "ERROR: Required source file is missing: $source_file"
            return 1
        fi
    done

    if ! find_supported_python; then
        return 1
    fi

    if ! confirm_action \
        "INSTALL" \
        "This installs a per-user Finder Quick Action and runtime under your Library folder."
    then
        print "Installation cancelled. No files were changed."
        return 0
    fi

    umask 077
    stage_root=$(/usr/bin/mktemp -d /tmp/quick-tunnel-install.XXXXXX)
    runtime_stage="$stage_root/runtime"
    workflow_stage="$stage_root/Share to Codex Review.workflow"
    /bin/mkdir -p -- "$runtime_stage" "$workflow_stage/Contents"

    /bin/cp -- "$script_directory/share-codex-review.py" "$runtime_stage/"
    /bin/cp -- "$script_directory/share-codex-review.command" "$runtime_stage/"
    /bin/cp -- "$script_directory/launch-from-finder.sh" "$runtime_stage/"
    /bin/cp -- "$safe_server_source" "$runtime_stage/"
    /bin/cp -- "$workflow_template/Contents/Info.plist" \
        "$workflow_stage/Contents/Info.plist"
    /bin/cp -- "$workflow_template/Contents/document.wflow" \
        "$workflow_stage/Contents/document.wflow"

    "$python_path" - "$runtime_stage/share-codex-review.py" <<'PYTHON'
import ast
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
PYTHON

    /usr/bin/plutil -lint "$workflow_stage/Contents/Info.plist"
    /usr/bin/plutil -lint "$workflow_stage/Contents/document.wflow"

    /bin/chmod 700 \
        "$runtime_stage/share-codex-review.command" \
        "$runtime_stage/launch-from-finder.sh"
    /bin/chmod 600 \
        "$runtime_stage/share-codex-review.py" \
        "$runtime_stage/safe-review-server.py" \
        "$workflow_stage/Contents/Info.plist" \
        "$workflow_stage/Contents/document.wflow"

    /bin/mkdir -p -- \
        "$HOME/Library/Application Support" \
        "$services_directory"
    move_to_del "$runtime_directory"
    move_to_del "$workflow_path"
    /bin/mv -- "$runtime_stage" "$runtime_directory"
    /bin/mv -- "$workflow_stage" "$workflow_path"
    /usr/bin/touch "$services_directory"
    refresh_services

    print "Finder Quick Action installed for the current user."
    print "If it is hidden, enable it in System Settings > Privacy & Security > Extensions > Finder."
    show_status
}

uninstall_action() {
    if [[ $(uname -s) != "Darwin" ]]; then
        print -u2 "ERROR: Finder Quick Action removal requires macOS."
        return 1
    fi

    if [[ ! -e "$runtime_directory" && ! -e "$workflow_path" ]]; then
        print "Finder Quick Action is not installed."
        return 0
    fi

    if ! confirm_action \
        "REMOVE" \
        "This removes the per-user Finder Quick Action using recoverable .del folders."
    then
        print "Removal cancelled. No files were changed."
        return 0
    fi

    move_to_del "$workflow_path"
    move_to_del "$runtime_directory"
    /usr/bin/touch "$services_directory"
    refresh_services
    print "Finder Quick Action removed. The previous files remain recoverable in sibling .del folders."
}

if [[ $# -lt 1 ]]; then
    usage
    exit 64
fi

action=$1
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes)
            skip_confirmation=1
            ;;
        *)
            usage
            exit 64
            ;;
    esac
    shift
done

case "$action" in
    doctor)
        doctor_action
        ;;
    install)
        install_action
        ;;
    uninstall)
        uninstall_action
        ;;
    status)
        show_status
        ;;
    *)
        usage
        exit 64
        ;;
esac
