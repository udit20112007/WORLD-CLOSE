#!/usr/bin/env bash
# Everything the GitHub workflow does, in one place, so future changes never need
# workflow edits.
#
#   bash scripts/ci_run.sh BACKFILL_DAYS all|EXCHANGE [EXCHANGE ...]
#
# Storage design: price data lives on a separate branch called "data" whose history
# is squashed to a single commit, and daily files older than WC_KEEP_DAYS (400) are
# deleted. Git normally keeps every version of every file forever; this way the
# repository stays roughly the same size instead of growing every year. The main
# branch only holds code.
#
# The first time it runs, it creates the data branch from the main branch's
# world-close-stage1/data folder (reusing the same stored files, so nothing is
# uploaded twice) and removes that folder from main.
#
# Each exchange is saved as soon as it's done, so a long run that gets cut off keeps
# everything finished so far. New exchanges stop being started after
# WC_TIME_BUDGET_MIN minutes (300), leaving time to build and publish the site.
set -u
backfill="${1:-0}"; shift
budget_min="${WC_TIME_BUDGET_MIN:-300}"
keep_days="${WC_KEEP_DAYS:-400}"
pause="${WC_PAUSE_SECONDS:-30}"
PY="${WC_PYTHON:-python}"

project="$(pwd)"                                   # the world-close-stage1 folder
root="$(git rev-parse --show-toplevel)"
rel="${project#"$root"/}"                          # world-close-stage1
data_wt="${RUNNER_TEMP:-$root/..}/wc-data"
start=$(date +%s)

git config user.name "github-actions[bot]"
git config user.email "41898283+github-actions[bot]@users.noreply.github.com"

# ---------------------------------------------------------------- data branch
# Fetched into a named ref: FETCH_HEAD would be overwritten by the git pull below
DATA_REF=refs/remotes/origin/data
if git ls-remote --exit-code --heads origin data >/dev/null 2>&1; then
  git fetch -q --depth 1 origin "+data:$DATA_REF"
else
  echo "No data branch yet: creating it from $rel/data on main."
  if git rev-parse -q --verify "HEAD:$rel/data" >/dev/null; then
    data_tree=$(git rev-parse "HEAD:$rel/data")
    root_tree=$(printf '040000 tree %s\tdata\n' "$data_tree" | git mktree)
  else
    root_tree=$(git mktree </dev/null)
  fi
  first=$(git commit-tree "$root_tree" -m "Price data (history squashed; see scripts/ci_run.sh)")
  git push -q origin "$first:refs/heads/data" || { echo "::error::Couldn't create the data branch"; exit 1; }
  git update-ref "$DATA_REF" "$first"
  if [ -d "$root/$rel/data" ] && git -C "$root" ls-files --error-unmatch "$rel/data" >/dev/null 2>&1; then
    git -C "$root" rm -r -q "$rel/data"
    git -C "$root" commit -q -m "Move price data to the data branch"
    git -C "$root" pull -q --rebase origin "$(git rev-parse --abbrev-ref HEAD)" && git -C "$root" push -q origin HEAD
    echo "Moved $rel/data from main to the data branch."
  fi
fi
rm -rf "$data_wt"
git worktree add -q --detach "$data_wt" "$DATA_REF"
# Safety check: the data branch must hold only the data folder
if [ -n "$(cd "$data_wt" && git ls-tree --name-only HEAD | grep -v '^data$')" ]; then
  echo "::error::The data branch contains files other than data/; stopping so nothing is overwritten."
  exit 1
fi
export WC_DATA_DIR="$data_wt/data"
mkdir -p "$WC_DATA_DIR"

save() {   # replace the data branch with one commit holding the current files
  ( cd "$data_wt" || exit 1
    git add -A .
    if git diff --cached --quiet; then exit 0; fi
    commit=$(git commit-tree "$(git write-tree)" -m "Price data, updated $(date -u '+%Y-%m-%d %H:%M UTC') ($1)")
    for attempt in 1 2 3; do
      if git push -q -f origin "$commit:refs/heads/data"; then git reset -q --soft "$commit"; exit 0; fi
      sleep 5
    done
    echo "::warning::Couldn't save the data branch after $1"
  )
}

# ---------------------------------------------------------------- update
if [ "${1:-all}" = "all" ]; then
  set -- $($PY -m pipeline.run exchanges)
fi
tried=0; failed=0; skipped=(); n=0
for ex in "$@"; do
  if [ "$backfill" != "0" ] && [ "$n" -gt 0 ]; then sleep "$pause"; fi   # let Yahoo's rate limit recover
  n=$((n + 1))
  elapsed_min=$(( ($(date +%s) - start) / 60 ))
  if [ "$elapsed_min" -ge "$budget_min" ]; then skipped+=("$ex"); continue; fi
  echo "::group::$ex (after ${elapsed_min} min)"
  tried=$((tried + 1))
  $PY -m pipeline.run update --exchanges "$ex" --backfill-days "$backfill" || failed=$((failed + 1))
  save "$ex"
  echo "::endgroup::"
done

$PY -m pipeline.run prune --keep-days "$keep_days" && save "pruned files older than $keep_days days"

# ---------------------------------------------------------------- site
$PY -m pipeline.run build || { echo "::error::Site build failed"; exit 1; }

if [ "${#skipped[@]}" -gt 0 ]; then
  echo "::warning::Time budget of ${budget_min} min reached. Not started this run: ${skipped[*]}. Run again with just these to finish."
fi
echo "Tried $tried exchange(s), $failed failed."
[ "$tried" -eq 0 ] || [ "$failed" -lt "$tried" ]
