#!/usr/bin/env bash
# Publishes the built documentation (sphinx/build/html: "ant doc" builds it)
# to the gh-pages branch, which GitHub Pages serves at
#   https://robkremer.github.io/semanticNets/
# The branch holds only the HTML, one commit per publish; main never does --
# and the models tools/publishModels.sh puts in its models folder, which this
# leaves alone.
#   tools/publishDocs.sh            commit to gh-pages, and push it to origin
#   tools/publishDocs.sh --no-push  just commit (eg: to look first)
set -euo pipefail

projectRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
html="${projectRoot}/sphinx/build/html"
push=1
[ "${1:-}" = "--no-push" ] && push=0

[ -f "${html}/index.html" ] || { echo "No ${html}/index.html: run \"ant doc\" first." >&2; exit 1; }

work="$(mktemp -d)"
pages="${work}/gh-pages"
trap 'git -C "${projectRoot}" worktree remove --force "${pages}" 2>/dev/null || true; rm -rf "${work}"' EXIT

cd "${projectRoot}"
source="$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- sphinx src plugins || echo '+changes')"
source "${projectRoot}/tools/ghPages.sh"
if ! ghPagesWorktree "${pages}"; then # (the first time: a branch with no history of its own)
  git worktree add --quiet --orphan -b gh-pages "${pages}"
fi

rsync -a --delete --exclude .git --exclude .DS_Store --exclude /models "${html}/" "${pages}/"
touch "${pages}/.nojekyll" # (serve the files as they are: Jekyll would hide _static, _images, ...)

git -C "${pages}" add --all
if git -C "${pages}" diff --cached --quiet; then
  echo "The documentation hasn't changed since it was last published."
else
  git -C "${pages}" commit --quiet -m "Documentation, from ${source}"
  echo "Committed the documentation to gh-pages (from ${source})."
fi

if [ "${push}" = 1 ]; then
  git -C "${pages}" push origin gh-pages
  echo "Published: https://robkremer.github.io/semanticNets/"
fi
