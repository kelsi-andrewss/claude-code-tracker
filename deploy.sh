#!/usr/bin/env bash
set -euo pipefail

REPO="kelsi-andrewss/claude-code-tracker"
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
FORMULA="$(cd "$(dirname "$0")" && pwd)/Formula/claude-code-tracker.rb"

current_version=$(grep '"version"' "$PACKAGE_JSON" | sed 's/.*: *"\([^"]*\)".*/\1/')
[[ -z "$current_version" ]] && die "could not read version from package.json"

IFS='.' read -r major minor patch <<< "$current_version"

# --- Compute new version ---

case "$BUMP" in
  patch) new_version="$major.$minor.$((patch + 1))" ;;
  minor) new_version="$major.$((minor + 1)).0" ;;
  major) new_version="$((major + 1)).0.0" ;;
  *)
    if [[ "$BUMP" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      new_version="$BUMP"
    else
      die "invalid bump type or version: $BUMP"
    fi
    ;;
esac

TAG="v$new_version"
TARBALL_URL="https://github.com/$REPO/archive/refs/tags/$TAG.tar.gz"

echo "=== Release Pipeline ==="
echo "  current: $current_version"
echo "  new:     $new_version ($TAG)"
echo ""

# --- Dry run shortcut ---

if $DRY_RUN; then
  echo "[dry-run] Would perform the following steps:"
  echo ""
  echo "  1. Preflight: verify clean tree, main branch, gh + npm available"
  echo "  2. Update package.json version to $new_version"
  echo "  3. Update Formula url to $TARBALL_URL"
  echo "  4. Commit: \"release $TAG\""
  echo "  5. Tag: $TAG"
  echo "  6. Push main + tags to origin"
  echo "  7. Create GitHub release $TAG with generated notes"
  echo "  8. Download tarball, compute SHA256, update Formula"
  echo "  9. Commit: \"update formula sha256 for $TAG\""
  echo "  10. Push formula update"
  echo "  11. npm publish"
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

command -v gh >/dev/null 2>&1 || die "gh CLI not found — install from https://cli.github.com"
command -v npm >/dev/null 2>&1 || die "npm not found"

echo "  branch: main"
echo "  tree: clean"
echo "  gh: $(gh --version | head -1)"
echo "  npm: $(npm --version)"
echo ""

# --- Bump version ---

echo "--- Bumping version to $new_version ---"

sed -i '' "s/\"version\": \"$current_version\"/\"version\": \"$new_version\"/" "$PACKAGE_JSON"
echo "  updated package.json"

sed -i '' "s|archive/refs/tags/v$current_version\.tar\.gz|archive/refs/tags/$TAG.tar.gz|" "$FORMULA"
echo "  updated Formula url"
echo ""

# --- Commit + tag ---

echo "--- Commit + tag ---"

git add "$PACKAGE_JSON" "$FORMULA"
git commit -m "release $TAG"
git tag "$TAG"
echo "  committed and tagged $TAG"
echo ""

# --- Push ---

echo "--- Push ---"

git push origin main --tags
echo "  pushed main + tags"
echo ""

# --- GitHub release ---

echo "--- GitHub release ---"

gh release create "$TAG" --generate-notes
echo "  created release $TAG"
echo ""

# --- Update Homebrew SHA256 ---

echo "--- Update formula SHA256 ---"

echo "  downloading tarball..."
tmpfile=$(mktemp)
trap "rm -f $tmpfile" EXIT

# wait a moment for GitHub to generate the tarball
sleep 3
curl -sL "$TARBALL_URL" -o "$tmpfile"

new_sha=$(shasum -a 256 "$tmpfile" | awk '{print $1}')
[[ -z "$new_sha" ]] && die "failed to compute SHA256"
echo "  sha256: $new_sha"

old_sha=$(grep 'sha256' "$FORMULA" | sed 's/.*"\([^"]*\)".*/\1/')
sed -i '' "s/$old_sha/$new_sha/" "$FORMULA"
echo "  updated Formula sha256"
echo ""

# --- Commit + push formula update ---

echo "--- Commit formula SHA ---"

git add "$FORMULA"
git commit -m "update formula sha256 for $TAG"
git push origin main
echo "  pushed formula update"
echo ""

# --- npm publish ---

echo "--- npm publish ---"

npm publish
echo "  published to npm"
echo ""

echo "=== Release $TAG complete ==="
