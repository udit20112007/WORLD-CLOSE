#!/usr/bin/env bash
# Update exchanges one at a time, saving each to the repository as soon as it's done,
# so a long run that gets cut off keeps everything finished so far.
#
#   bash scripts/update_and_save.sh BACKFILL_DAYS EXCHANGE [EXCHANGE ...]
#
# Stops starting new exchanges after WC_TIME_BUDGET_MIN minutes (default 300), leaving
# time to build and publish the site before GitHub's 6-hour limit. Skipped exchanges
# are picked up by the next run. Exits 1 only if every exchange it tried failed.
set -u
backfill="${1:-0}"; shift
budget_min="${WC_TIME_BUDGET_MIN:-300}"
start=$(date +%s)
tried=0; failed=0; skipped=()

git config user.name "github-actions[bot]"
git config user.email "41898283+github-actions[bot]@users.noreply.github.com"

for ex in "$@"; do
  elapsed_min=$(( ($(date +%s) - start) / 60 ))
  if [ "$elapsed_min" -ge "$budget_min" ]; then
    skipped+=("$ex"); continue
  fi
  echo "::group::$ex (after ${elapsed_min} min)"
  tried=$((tried + 1))
  if ! python -m pipeline.run update --exchanges "$ex" --backfill-days "$backfill"; then
    failed=$((failed + 1))
  fi
  mkdir -p data
  git add data
  if ! git diff --cached --quiet; then
    git commit -q -m "Data: $ex $(date -u +%Y-%m-%d)"
    for attempt in 1 2 3; do
      git pull -q --rebase --autostash && git push -q && break
      sleep 5
    done
  fi
  echo "::endgroup::"
done

if [ "${#skipped[@]}" -gt 0 ]; then
  echo "::warning::Time budget of ${budget_min} min reached. Not started this run: ${skipped[*]}. Run again with just these to finish."
fi
echo "Tried $tried exchange(s), $failed failed."
[ "$tried" -eq 0 ] || [ "$failed" -lt "$tried" ]
