#!/bin/sh
set -eu

load_secret() {
    variable="$1"
    file_variable="${variable}_FILE"
    eval "secret_file=\${${file_variable}:-}"
    if [ -n "$secret_file" ]; then
        if [ ! -f "$secret_file" ]; then
            echo "required secret file is missing: $file_variable" >&2
            exit 1
        fi
        secret_value="$(cat "$secret_file")"
        if [ -z "$secret_value" ]; then
            echo "required secret file is empty: $file_variable" >&2
            exit 1
        fi
        export "$variable=$secret_value"
        unset secret_value
    fi
}

load_secret SUPABASE_SECRET_KEY
load_secret VIEWER_CODE
load_secret ADMIN_CODE
load_secret BFF_ACTOR_NAMESPACE_SECRET
load_secret BFF_CSRF_SECRET

verify_writable_volumes() {
    paths="${PNL_VOLUME_CANARY_PATHS:-}"
    [ -n "$paths" ] || return 0
    old_ifs="$IFS"
    IFS=:
    for path in $paths; do
        [ -n "$path" ] || continue
        if [ ! -d "$path" ]; then
            echo "required writable volume is missing: $path" >&2
            exit 1
        fi
        canary="$(mktemp "$path/.pnl-volume-canary.XXXXXX")"
        printf '%s' 'pnl-volume-canary-v1' > "$canary"
        if [ "$(cat "$canary")" != 'pnl-volume-canary-v1' ]; then
            rm -f "$canary"
            echo "writable volume readback failed: $path" >&2
            exit 1
        fi
        rm -f "$canary"
        [ ! -e "$canary" ] || {
            echo "writable volume cleanup failed: $path" >&2
            exit 1
        }
    done
    IFS="$old_ifs"
    echo "volume_canary=pass uid=$(id -u) path_count=$(printf '%s' "$paths" | awk -F: '{print NF}')"
}

verify_writable_volumes

exec "$@"
