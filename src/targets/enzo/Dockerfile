# syntax=docker/dockerfile:1.17

FROM aflplusplus/aflplusplus@sha256:b1a08b5d26b8944a4a7b912672b60ae8d09726a0928c6ed6562679821c905232 AS base
RUN apt update -y
RUN apt install -y screen python3 fish neovim gdb curl patch git lsb-release build-essential rustup strace linux-tools-generic jq sloccount
RUN rustup default stable
COPY --from=golang:1.24.1@sha256:52ff1b35ff8de185bf9fd26c70077190cd0bed1e9f16a2d498ce907e5c421268 /usr/local/go/ /usr/local/go/
COPY --from=ghcr.io/astral-sh/uv@sha256:144717a043a150a04f05d0af58f6a6f46e23b76b8744f52c7baf8523d6057b56 /usr/local/bin/uv /usr/local/bin/uvx /bin/
ENV PATH="$PATH:/usr/local/go/bin/"


FROM scratch AS just-dl
ARG JUST_VERSION=1.43.0
ARG JUST_SUM=sha256:a1bc93654f31669fd964ea3011a5e5e9676b9b6f8adcd762606e5140632ea72d
ADD --checksum=$JUST_SUM --unpack=true https://github.com/casey/just/releases/download/$JUST_VERSION/just-$JUST_VERSION-x86_64-unknown-linux-musl.tar.gz /root/just


FROM base AS afltriage-build
ARG ALFT_COMMIT=e86d323d1d807185da0ec3cd3aad892058c7d3a8
ADD --checksum=$ALFT_COMMIT --keep-git-dir=true https://github.com/quic/AFLTriage.git#$ALFT_COMMIT /root/AFLTriage
COPY common/afltriage.patch /root/
WORKDIR /root/AFLTriage/
RUN patch -p1 < ../afltriage.patch
RUN cargo install --locked --path .


FROM base AS crashwalk-build
ARG CW_COMMIT=2338abf87accac5ec1a88458bd5ea5858d2fe8b2
ADD --checksum=$CW_COMMIT --keep-git-dir=true https://github.com/bnagy/crashwalk.git#$CW_COMMIT /root/crashwalk
COPY common/crashwalk.patch /root/
WORKDIR /root/crashwalk/
RUN patch -p1 < ../crashwalk.patch
RUN CGO_ENABLED=0 go install crashwalk/cmd/cwtriage
RUN CGO_ENABLED=0 go install crashwalk/cmd/cwfind
RUN CGO_ENABLED=0 go install crashwalk/cmd/cwdump


FROM base AS exploitable-build
ARG EXPL_COMMIT=f8f2dd4ce31141ba4f5eb93def8681c5aa739690
# updated version of https://github.com/jfoote/exploitable
ADD --checksum=$EXPL_COMMIT --keep-git-dir=true https://github.com/skirge/exploitable.git#$EXPL_COMMIT /root/exploitable
COPY common/exploitable-rc0r-batchability.patch /root/
WORKDIR /root/exploitable/
RUN patch --forward -p1 < ../exploitable-rc0r-batchability.patch
RUN pip install setuptools tqdm
RUN python setup.py install


FROM base AS harness-components-build
COPY common/harness/ /root/harness/
RUN mkdir -p /root/harness/build/lib/
RUN c++ -Wall -Wextra -Werror -shared -fPIC -o /root/harness/build/lib/libfopen_hook.so /root/harness/fopen_hook.cpp -ldl -g


FROM base AS enzo-build-run-common
RUN apt install -y bc libhdf5-dev gfortran
COPY --from=harness-components-build /root/harness/build/lib/ /usr/lib/
COPY --from=just-dl /root/just/just /usr/local/bin/just
RUN make install


FROM enzo-build-run-common AS enzo-build
ENV PATH="/AFLplusplus:$PATH"
ENV CC="/AFLplusplus/afl-clang-lto"
ENV CXX="/AFLplusplus/afl-clang-lto++"
ENV LD="/AFLplusplus/afl-ld-lto"
RUN ln -s /AFLplusplus/afl-clang-lto   /AFLplusplus/gcc
RUN ln -s /AFLplusplus/afl-clang-lto++ /AFLplusplus/g++
RUN ln -s /AFLplusplus/afl-clang-lto   /AFLplusplus/clang
RUN ln -s /AFLplusplus/afl-clang-lto++ /AFLplusplus/clang++
RUN ln -s /AFLplusplus/afl-clang-lto   /AFLplusplus/cc
RUN ln -s /AFLplusplus/afl-clang-lto++ /AFLplusplus/c++
RUN ln -s /AFLplusplus/afl-ld-lto      /AFLplusplus/ld
RUN ln -sf /usr/lib/llvm-19/bin/llvm-ar /usr/bin/llvm-ar
WORKDIR /root/sci-apps-fuzz/build/enzo
ARG ENZO_COMMIT=a1346e1bf978d45546efa69f57886e2d99f985ad
ADD --checksum=$ENZO_COMMIT --keep-git-dir=true https://github.com/enzo-project/enzo-dev.git#$ENZO_COMMIT enzo-dev
WORKDIR enzo-dev


FROM enzo-build AS enzo-build-fast
COPY targets/enzo/fuzzable.patch .
RUN patch --forward -p1 < fuzzable.patch
RUN ./configure
RUN make -C src/enzo machine-ubuntu
RUN make -C src/enzo CONFIG_USE_MPI=no clean
RUN AFL_HARDEN=1 make -C src/enzo -j 16 CONFIG_USE_MPI=no
RUN cp src/enzo/enzo.exe ../enzo-fast.exe


FROM enzo-build AS enzo-build-slow
COPY targets/enzo/fuzzable.patch .
RUN patch --forward -p1 < fuzzable.patch
RUN ./configure
RUN make -C src/enzo machine-ubuntu
RUN make -C src/enzo CONFIG_USE_MPI=no clean
RUN AFL_USE_ASAN=1 make -C src/enzo -j 16 CONFIG_USE_MPI=no
RUN cp src/enzo/enzo.exe ../enzo-slow.exe


FROM enzo-build AS enzo-build-vanilla
COPY targets/enzo/vanilla-compat.patch .
RUN patch --forward -p1 --ignore-whitespace < vanilla-compat.patch
RUN ./configure
RUN make -C src/enzo machine-ubuntu
RUN make -C src/enzo -j 16 CONFIG_USE_MPI=no
RUN cp src/enzo/enzo.exe ../enzo-vanilla.exe


FROM enzo-build-run-common AS enzo-run
COPY --from=afltriage-build /root/.cargo/bin/ /root/.cargo/bin/
COPY --from=crashwalk-build /root/go/ /root/go/
COPY --from=exploitable-build /root/exploitable /root/exploitable

WORKDIR /root/sci-apps-fuzz/src/
COPY common common
WORKDIR common
RUN ./setup-utils.sh

COPY --from=enzo-build-slow /root/sci-apps-fuzz/build/enzo /root/sci-apps-fuzz/build/enzo/slow/
COPY --from=enzo-build-fast /root/sci-apps-fuzz/build/enzo /root/sci-apps-fuzz/build/enzo/fast/
COPY --from=enzo-build-vanilla /root/sci-apps-fuzz/build/enzo /root/sci-apps-fuzz/build/enzo/vanilla/
ENV BIN_SLOW=/root/sci-apps-fuzz/build/enzo/slow/enzo-slow.exe
ENV BIN_FAST=/root/sci-apps-fuzz/build/enzo/fast/enzo-fast.exe
ENV BIN_VANILLA=/root/sci-apps-fuzz/build/enzo/vanilla/enzo-vanilla.exe

WORKDIR /root/sci-apps-fuzz/src/
COPY targets/enzo targets/enzo
COPY justfile justfile

ENV APP_NAME=enzo
RUN cat common/fish_greeting >> /root/.config/fish/config.fish

CMD ["fish"]
