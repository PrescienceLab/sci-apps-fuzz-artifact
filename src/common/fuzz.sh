#!/bin/bash
set -euxo pipefail

source targets/$1/target_parameters.sh
source common/generic_parameters.sh
TESTCASES=$(readlink -e targets/$1/testcases/)

HOST_SYNC_DIR=$(readlink -m $3)
SYNC_DIR=$(readlink -m $2)
GL_SYNC_SCRIPT=$(readlink -e common/sync.sh)
mkdir -p ${SYNC_DIR}
cd ${SYNC_DIR}

export AFL_AUTORESUME=1
LOG=/dev/null

if [ -v AFL_DEBUG ]; then
  LOG=fuzzer-master-${HOSTNAME}.log
fi
nice -n19 afl-fuzz -i ${TESTCASES} -o ${SYNC_DIR} -M fuzzer-master-${HOSTNAME} -t $((100*${TIME_LIM})) -- ${BIN_SLOW} ${ARGS} > ${LOG} &

for ((i = 1; i <= ${NPROC_FUZZ}; i++))
do
  if [ -v AFL_DEBUG ]; then
    LOG=fuzzer-${i}-${HOSTNAME}.log
  fi
  nice -n19 afl-fuzz -i ${TESTCASES} -o ${SYNC_DIR} -S fuzzer-${i}-${HOSTNAME} -t ${TIME_LIM} -w ${BIN_SLOW} -- ${BIN_FAST} ${ARGS} > ${LOG} &
done

$GL_SYNC_SCRIPT ${HOST_SYNC_DIR} ${SYNC_DIR} > /dev/null 2>&1 &

watch "ps -e | grep sync.sh || echo 'sync not running'; afl-whatsup -s ${SYNC_DIR}"
