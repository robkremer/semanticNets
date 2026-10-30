# Sourced by tools/publishDocs.sh and tools/publishModels.sh (not run itself).
#   ghPagesWorktree DIR
# checks the gh-pages branch out at DIR (a new worktree of the repository in
# the current directory), caught up with origin's first: the docs and models
# can be published from more than one machine, and each one's gh-pages is
# behind whatever the others pushed since, which origin would refuse.
# Returns 1 if there's no gh-pages here or on origin yet.

ghPagesWorktree() {
  local pages="$1" remote="" here=""
  if git fetch --quiet origin gh-pages 2>/dev/null; then
    remote="$(git rev-parse FETCH_HEAD)"
  elif git ls-remote --heads origin >/dev/null 2>&1; then
    : # (origin has no gh-pages yet)
  else
    echo "(Couldn't reach origin: going on with this machine's copy of gh-pages.)" >&2
  fi
  git show-ref --verify --quiet refs/heads/gh-pages && here="$(git rev-parse gh-pages)"

  if [ -n "${remote}" ] && [ -n "${here}" ] && [ "${here}" != "${remote}" ]; then
    if git merge-base --is-ancestor "${here}" "${remote}"; then
      git branch --quiet --force gh-pages "${remote}" # (just behind: catch up)
    elif ! git merge-base --is-ancestor "${remote}" "${here}"; then
      # Both have commits the other hasn't (eg: an unpushed --no-push here).
      # Start again from origin's -- what's being published now is copied
      # in afresh anyway -- and keep this machine's under another name.
      local keep="gh-pages-unpushed-$(date +%Y%m%d-%H%M%S)"
      git branch --quiet "${keep}" "${here}"
      git branch --quiet --force gh-pages "${remote}"
      echo "This machine's gh-pages had commits origin hasn't, and origin had newer ones: kept this machine's as branch ${keep}, and started from origin's." >&2
    fi # (else just ahead: push adds to it)
    here=gh-pages
  fi

  if [ -n "${here}" ]; then
    git worktree add --quiet "${pages}" gh-pages
  elif [ -n "${remote}" ]; then
    git worktree add --quiet -b gh-pages "${pages}" "${remote}"
  else
    return 1
  fi
}
