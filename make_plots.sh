#!/bin/bash
set -euxo pipefail

do_plots_all() {
  CONTEXT=$1
  MEM_LIM=$(( 128 * 256 ))

  docker --context $CONTEXT buildx build --shm-size="${MEM_LIM}m" --tag sciattack-plot -f src/common/Dockerfile.plot src/

  docker --context $CONTEXT run \
    --interactive \
    --tty \
    --memory="${MEM_LIM}m" \
    --memory-swap="0m" \
    --tmpfs /tmp/:size=${MEM_LIM}m,exec \
    -v $SHARED_FUZZ_FS/:/mnt/shared-fuzz-fs/ \
    sciattack-plot:latest \
    fish -c "just plot-all"

  echo "plots written to:"
  echo $SHARED_FUZZ_FS
}

do_plots_all $1
