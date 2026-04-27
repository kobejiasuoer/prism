#!/bin/bash

prism_init_artifact_helpers() {
  PRISM_REPO_ROOT="$1"
  PRISM_RUN_STAMP="${2:-}"
  PRISM_ARTIFACT_TRADE_DATE="${3:-$(date "+%F")}"
}

prism_artifact_enabled() {
  [[ "${PRISM_MIRROR_ARTIFACTS:-1}" == "1" || "${PRISM_MIRROR_ARTIFACTS:-1}" == "true" ]]
}

prism_artifact_generated_at() {
  local stamp="${PRISM_RUN_STAMP:-}"
  local date_part time_part
  if [[ "$stamp" == *_* ]]; then
    date_part="${stamp%%_*}"
    time_part="${stamp#*_}"
    time_part="${time_part%%_*}"
    time_part="${time_part//-/:}"
    echo "$date_part $time_part"
    return 0
  fi
  date "+%F %T"
}

prism_register_artifact() {
  local path="$1"
  local artifact_type="$2"
  local source="${3:-screener}"
  local generated_at
  generated_at="$(prism_artifact_generated_at)"
  if [[ ! -f "$path" ]]; then
    return 0
  fi
  PYTHONPATH="$PRISM_REPO_ROOT:$PRISM_REPO_ROOT/packages:${PYTHONPATH:-}" \
    python3 -m prism_storage.cli \
      --repo-root "$PRISM_REPO_ROOT" \
      register-file "$path" \
      --artifact-type "$artifact_type" \
      --source "$source" \
      --trade-date "$PRISM_ARTIFACT_TRADE_DATE" \
      --generated-at "$generated_at" \
      --metadata-json "{\"run_stamp\":\"${PRISM_RUN_STAMP:-}\"}" >/dev/null 2>&1 || true
}

prism_mirror_artifact() {
  local source_path="$1"
  local relative_target="$2"
  local artifact_type="$3"
  local source="${4:-screener}"
  local target_path="$PRISM_REPO_ROOT/data/artifacts/$relative_target"
  if ! prism_artifact_enabled || [[ ! -f "$source_path" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$target_path")"
  cp "$source_path" "$target_path"
  prism_register_artifact "$target_path" "$artifact_type" "$source"
  echo "  artifact -> $target_path"
}
