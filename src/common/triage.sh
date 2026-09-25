#!/bin/bash
set -euxo pipefail

source targets/$1/target_parameters.sh
source common/generic_parameters.sh

SYNC_DIR=$2
TRIAGE_DIR=$3

mkdir -p ${TRIAGE_DIR}/{afltriage/,cw/,plots/}
cd $(mktemp -d)
nice -n19 afltriage -i ${SYNC_DIR}/fuzzer*/crashes*/ -o ${TRIAGE_DIR}/afltriage/ --jobs ${NPROC_TRIAGE} --report-formats json --child-output --child-output-lines 500 --stdin -- ${BIN_SLOW} ${ARGS}
nice -n19 cwtriage -match crashes.\*id -root ${SYNC_DIR} -workers ${NPROC_TRIAGE} -output json -- ${BIN_SLOW} ${ARGS} > ${TRIAGE_DIR}/cw/crashes.json
