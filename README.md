# sci-apps-fuzz

AFL++ fuzz harnesses + utils for scientific applications

## Prerequisites

Installed on the host machine:

- `bash`
- `docker`
- `docker buildx`

You can use Docker's remote contexts feature to delegate fuzzing workloads to other machines.

## Usage

1. Make a directory to store fuzzer data.
This directory will grow large, so place it on an appropriate filesystem.

    Set the variable

    ```bash
    export SHARED_FUZZ_FS=/path/to/my/directory
    ```

    Note that when using a remote Docker context, this path is a remote path.

2. Use the convenience script to build and run the container with Docker:

    ```bash
    ./run_with_docker.sh $APPLICATION_NAME $CONTEXT $CPUS
    ```

    where `$APPLICATION_NAME` is the name of a target in `src/targets/`, `$CONTEXT` is the name of the Docker context you wish to use (`default`, if you did not configure a remote context), and `$CPUS` is the set or range of CPUs to which to limit the container (eg. `0`, `3,4`, `16-31`, etc.).

3. Inside the container, use `just` to invoke the recipes in the `justfile`.
Remember to keep CPU, memory, and disk usage under control.
You can safely background the watcher interface with ^Z, and resume with `fg`.

    For more details, see the appendix of [our SC'26 workshop paper](https://buoyancy-project.org/papers/casa-shpc26.pdf).
