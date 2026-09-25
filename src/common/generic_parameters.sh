#!/bin/bash

NPROC_FUZZ=$(nproc --ignore 1)
NPROC_TRIAGE=$(nproc --ignore 1)
export AFL_PRELOAD=/usr/lib/libfopen_hook.so

export ASAN_OPTIONS=detect_odr_violation=0:allocator_may_return_null=1:abort_on_error=1:symbolize=0:detect_leaks=0:alloc_dealloc_mismatch=0
