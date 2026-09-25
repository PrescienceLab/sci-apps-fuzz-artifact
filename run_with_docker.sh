#!/bin/bash
set -euxo pipefail

APP_NAME=$1
CONTEXT=$2
CPUS=$3
# EXTRA_ARGS="${@:4}"  # passed to `docker run`

MEM_LIM="${MEM_LIM:-$((128 * 256))}" # default 32G

docker --context $CONTEXT buildx build --shm-size="${MEM_LIM}m" --tag ${APP_NAME}-fuzz -f src/targets/${APP_NAME}/Dockerfile src/

# Note that you can use `docker context` to build and/or run this container on a remote machine.
# Before running this script, use `docker context use ...` to switch.

docker --context $CONTEXT run \
  --cap-add=SYS_PTRACE \
  --security-opt seccomp=unconfined \
  --interactive \
  --init \
  --tty \
  --cpuset-cpus=$CPUS \
  -e CPUS="$CPUS" \
  --memory="${MEM_LIM}m" \
  --memory-swap="0m" \
  --tmpfs /tmp/:size=${MEM_LIM}m,exec \
  -v $SHARED_FUZZ_FS/:/mnt/shared-fuzz-fs/ \
  ${APP_NAME}-fuzz:latest \
  "${@:4}"
