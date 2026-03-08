#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=false

die() { echo "error: $1" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: ./deploy.sh [--dry-run] <patch|minor|major|X.Y.Z>

Examples:
  ./deploy.sh patch        # 1.0.0 -> 1.0.1
  ./deploy.sh minor        # 1.0.0 -> 1.1.0
  ./deploy.sh major        # 1.0.0 -> 2.0.0
  ./deploy.sh 1.2.3        # explicit version
  ./deploy.sh --dry-run patch
EOF
  exit 1
}

# --- Parse args ---

[[ $# -eq 0 ]] && usage

if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  shift
fi

[[ $# -eq 0 ]] && usage
BUMP="$1"

# --- Read current version ---

PACKAGE_JSON="$(cd "$(dirname "$0")" && pwd)/package.json"

current_version=$(grep '"version"' "$PACKAGE_JSON" | sed 's/.*: *"\([^"]*\)".*/\1/')
[[ -z "$current_version" ]] && die "could not read version from package.json"

IFS='.' read -r major minor patch <<< "$current_version"

# --- Compute new version ---

case "$BUMP" in
  patch) new_version="$major.$minor.$((patch + 1))" ;;
  minor) new_version="$major.$((minor + 1)).0" ;;
  major) new_version="$((major + 1)).0.0" ;;
  *)
    if [[ "$BUMP" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
      new_version="$BUMP"
    else
      die "invalid bump type or version: $BUMP"
    fi
    ;;
esac

TAG="v$new_version"

echo "=== Release Pipeline ==="
echo "  current: $current_version"
echo "  new:     $new_version ($TAG)"
echo ""

# --- Dry run shortcut ---

if $DRY_RUN; then
  echo "[dry-run] Would perform the following steps:"
  echo ""
  echo "  1. Preflight: verify clean tree, main branch"
  echo "  2. Update package.json version to $new_version"
  echo "  3. Commit: \"release $TAG\""
  echo "  4. Tag: $TAG"
  echo "  5. Push main + $TAG to origin (triggers CI)"
  echo ""
  echo "  CI will then: run tests, npm publish, create GitHub release"
  echo ""
  echo "[dry-run] No changes made."
  exit 0
fi

# --- Preflight checks ---

echo "--- Preflight checks ---"

branch=$(git rev-parse --abbrev-ref HEAD)
[[ "$branch" != "main" ]] && die "must be on main branch (currently on $branch)"

if [[ -n "$(git status --porcelain)" ]]; then
  die "working tree is not clean — commit or stash changes first"
fi

echo "  branch: main"
echo "  tree: clean"
echo ""

# --- Bump version ---

echo "--- Bumping version to $new_version ---"

sed -i '' "s/\"version\": \"$current_version\"/\"version\": \"$new_version\"/" "$PACKAGE_JSON"
echo "  updated package.json"

echo ""

# --- Commit + tag ---

echo "--- Commit + tag ---"

git add "$PACKAGE_JSON"
git commit -m "release $TAG"
git tag "$TAG"
echo "  committed and tagged $TAG"
echo ""

# --- Push ---

echo "--- Push ---"

read -rp "Pushing $TAG will trigger CI to publish. Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "aborted."; exit 1; }

git push origin main "$TAG"
echo "  pushed main + $TAG"
echo ""

echo "=== Release $TAG started ==="
echo "  CI will handle: npm publish, GitHub release, Homebrew tap (if stable)"
