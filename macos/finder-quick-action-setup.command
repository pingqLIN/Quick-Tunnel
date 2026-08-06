#!/bin/zsh

set -u

script_directory=$(cd -- "$(dirname -- "$0")" && pwd)
manager="$script_directory/manage-finder-quick-action.sh"

print
print "Quick Tunnel Review Share - Finder Quick Action"
print "  1. Install"
print "  2. Remove"
print "  3. Show status"
print "  4. Run doctor"
print "  5. Cancel"
print
read "choice?Select [1-5]: "

case "$choice" in
    1)
        /bin/zsh "$manager" install
        result=$?
        ;;
    2)
        /bin/zsh "$manager" uninstall
        result=$?
        ;;
    3)
        /bin/zsh "$manager" status
        result=$?
        ;;
    4)
        /bin/zsh "$manager" doctor
        result=$?
        ;;
    *)
        exit 0
        ;;
esac

read "acknowledgement?Press RETURN to close this window"
exit $result
