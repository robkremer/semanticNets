#!/usr/bin/env bash
# Publishes a folder of models and views (.snm, .snv, ...) to the models folder
# of the gh-pages branch, which GitHub Pages serves at
#   https://robkremer.github.io/semanticNets/models/
# so sn can open them from there (read-only). The models folder is a mirror of
# the given folder: what's gone from it is removed from the site too. It's kept
# apart from the documentation: tools/publishDocs.sh leaves it alone, and the
# builds (.github/workflows/build.yml) drop it from the Help they bundle.
#   tools/publishModels.sh FOLDER            commit to gh-pages, and push it to origin
#   tools/publishModels.sh --no-push FOLDER  just commit (eg: to look first)
#   tools/publishModels.sh --force FOLDER    publish even if they refer to files elsewhere
# Models and views refer to the ones in the same folder (or below, or a few
# folders up) by relative names, so those keep working on the web; a reference
# to a file anywhere else (a "file:" URL) won't be found there, so it's listed,
# and nothing is published.
set -euo pipefail

projectRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
site="https://robkremer.github.io/semanticNets/models/"
push=1
force=0
while [ $# -gt 1 ]; do
  case "$1" in
    --no-push) push=0; shift ;;
    --force) force=1; shift ;;
    *) break ;;
  esac
done
[ $# = 1 ] && [ -d "$1" ] || { echo "Usage: $0 [--no-push] [--force] FOLDER (of the models and views to publish)" >&2; exit 1; }
models="$(cd "$1" && pwd)"

# References the web copies can't follow: "file:" URLs, other than a file's own
# URL and where it was copied from (sn takes the one it was read from instead).
# A model whose objects refer to a file on this computer would only work here,
# so nothing is published while there are any (unless --force).
found=0
while IFS= read -r -d '' f; do
  others="$(grep -v -e 'key="url"' -e 'key="previousURL"' "$f" | grep -o 'value="file:[^"]*"' \
            | sed -e 's/#[^"]*"$/"/' | sort | uniq -c || true)" # (each file once, with how many references to it)
  if [ -n "${others}" ]; then
    [ "${found}" = 1 ] || echo "These refer to files that won't be on the web (copy them into ${models}, and make the referring ones refer to the copies -- eg: Edit | Replace super-model...):"
    found=1
    echo "  ${f#"${models}/"}:"
    sed -e 's/^ *\([0-9]*\) value="\(.*\)"$/    \2 (\1)/' <<< "${others}"
  fi
done < <(find "${models}" -type f \( -name '*.snm' -o -name '*.snv' \) -print0)
if [ "${found}" = 1 ] && [ "${force}" = 0 ]; then
  echo "Nothing was published. (To publish anyway: $0 --force ...)" >&2
  exit 1
fi

work="$(mktemp -d)"
pages="${work}/gh-pages"
trap 'git -C "${projectRoot}" worktree remove --force "${pages}" 2>/dev/null || true; rm -rf "${work}"' EXIT

cd "${projectRoot}"
source "${projectRoot}/tools/ghPages.sh"
if ! ghPagesWorktree "${pages}"; then
  echo "There's no gh-pages branch yet: publish the documentation first (tools/publishDocs.sh)." >&2
  exit 1
fi

mkdir -p "${pages}/models"
rsync -a --delete --exclude .git --exclude .DS_Store --exclude '*.orig' --exclude '*~' "${models}/" "${pages}/models/"

git -C "${pages}" add --all models
if git -C "${pages}" diff --cached --quiet; then
  echo "The models haven't changed since they were last published."
else
  git -C "${pages}" commit --quiet -m "Models, from ${models}"
  echo "Committed the models to gh-pages:"
  git -C "${pages}" show --stat --format= HEAD | sed 's/^/  /'
fi

if [ "${push}" = 1 ]; then
  git -C "${pages}" push origin gh-pages
  echo "Published (GitHub Pages takes a minute or so): ${site}"
fi
