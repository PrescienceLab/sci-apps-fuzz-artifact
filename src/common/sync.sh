#!/bin/bash
set -euxo pipefail

shopt -s nullglob

LOCKDIR=/root/sync-script-lock
GLOBAL_SYNCDIR=$1
LOCAL_SYNCDIR=$2

#Remove the lock directory
cleanup() {
  if rmdir -- "$LOCKDIR"; then
    echo "Finished"
  else
    echo >&2 "Failed to remove lock directory '$LOCKDIR'"
    exit 1
  fi
}

if mkdir -- "$LOCKDIR"; then
  #Ensure that if we "grabbed a lock", we release it
  #Works for SIGTERM and SIGINT(Ctrl-C) as well in some shells
  #including bash.
  trap "cleanup" EXIT

  echo "Acquired lock, running"

  mkdir -p "$GLOBAL_SYNCDIR"

  while /bin/true; do
    if [ -d "$GLOBAL_SYNCDIR" ]; then
      echo "$GLOBAL_SYNCDIR exists"
      for subdir in ${GLOBAL_SYNCDIR}/fuzzer-master-*/; do
        subname=$(basename "$subdir")
        if [[ $subname != *-$HOSTNAME ]]; then
          cp -auv "$subdir" ${LOCAL_SYNCDIR}/ || true
        fi
      done
      cp -auv ${LOCAL_SYNCDIR}/fuzzer-*-$HOSTNAME/ ${GLOBAL_SYNCDIR}/ || true
    fi
    sleep 60
  done
else
  echo >&2 "Could not create lock directory '$LOCKDIR'"
  exit 1
fi
