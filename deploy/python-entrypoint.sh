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

exec "$@"
