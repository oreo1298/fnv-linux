#!/usr/bin/env bash
# Fetch fnv_decomp at the pinned commit into upstream/fnv_decomp (gitignored).
#
# The checkout is treated as read-only input: transforms never modify it, they
# write to a separate working tree. Re-running this script is safe; it verifies
# an existing checkout and only fetches when the pinned commit is missing.
#
# Usage: scripts/fetch-upstream.sh [DEST]
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pin_file="$root/upstream.pin"
dest="${1:-$root/upstream/fnv_decomp}"

url="$(sed -n 's/^url=//p' "$pin_file")"
commit="$(sed -n 's/^commit=//p' "$pin_file")"
if [[ -z "$url" || ! "$commit" =~ ^[0-9a-f]{40}$ ]]; then
    echo "error: $pin_file must define url= and a 40-hex commit=" >&2
    exit 1
fi

if [[ -d "$dest/.git" ]]; then
    have="$(git -C "$dest" rev-parse HEAD 2>/dev/null || true)"
    if [[ "$have" == "$commit" ]]; then
        if [[ -n "$(git -C "$dest" status --porcelain)" ]]; then
            echo "error: $dest has local modifications; upstream must stay pristine." >&2
            echo "       Run 'git -C \"$dest\" status' to inspect, then reset or re-clone." >&2
            exit 1
        fi
        echo "upstream already at $commit: $dest"
        exit 0
    fi
    echo "updating $dest from ${have:-<none>} to $commit"
else
    echo "cloning $url at $commit into $dest"
    mkdir -p "$dest"
    git -C "$dest" init -q
    git -C "$dest" remote add origin "$url"
fi

# Fetch exactly the pinned commit (GitHub allows fetching reachable SHAs).
fetched=0
for attempt in 1 2 3 4; do
    if git -C "$dest" fetch -q --depth 1 origin "$commit"; then
        fetched=1
        break
    fi
    echo "fetch failed (attempt $attempt), retrying..." >&2
    sleep $((attempt * 2))
done
if [[ $fetched -ne 1 ]]; then
    echo "error: could not fetch $commit from $url" >&2
    exit 1
fi
git -C "$dest" -c advice.detachedHead=false checkout -q --force "$commit"

have="$(git -C "$dest" rev-parse HEAD)"
if [[ "$have" != "$commit" ]]; then
    echo "error: checkout is at $have, expected $commit" >&2
    exit 1
fi
echo "upstream ready at $commit: $dest"
