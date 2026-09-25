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


FROM base AS gromacs-build-run-common
RUN apt install -y bc cmake
COPY --from=harness-components-build /root/harness/build/lib/ /usr/lib/
COPY --from=just-dl /root/just/just /usr/local/bin/just
RUN make install


FROM gromacs-build-run-common AS gromacs-build
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
WORKDIR /root/sci-apps-fuzz/build/gromacs
ARG CMAKE_VERSION=4.0.0
ARG CMAKE_SUM=a06e6e32da747e569162bc0442a3fd400fadd9db7d4f185c9e4464ab299a294b
ARG GROMACS_SUM=0adf621a80fd8043f8defec84ce02811c0cdf42a052232890932d81f25c4d28a
ADD --checksum=sha256:$CMAKE_SUM --unpack=true https://github.com/Kitware/CMake/releases/download/v$CMAKE_VERSION/cmake-$CMAKE_VERSION-linux-x86_64.tar.gz cmake-$CMAKE_VERSION
RUN cp -r cmake-$CMAKE_VERSION/* /usr/
ADD --checksum=sha256:$GROMACS_SUM --unpack=true https://ftp.gromacs.org/gromacs/gromacs-2025.1.tar.gz .
WORKDIR gromacs-2025.1/


FROM gromacs-build AS gromacs-build-fast
COPY targets/gromacs/fuzzable.patch .
RUN patch --forward -p1 < fuzzable.patch
WORKDIR build-fast
RUN cmake .. -DGMX_BUILD_OWN_FFTW=ON -DBUILD_SHARED_LIBS=OFF -DGMX_PREFER_STATIC_LIBS=ON -DCMAKE_INSTALL_PREFIX=$(readlink -m ../out-fast/)
RUN AFL_HARDEN=1 make -j 16 | tee build.log 2>&1
RUN make install


FROM gromacs-build AS gromacs-build-slow
COPY targets/gromacs/fuzzable.patch .
RUN patch --forward -p1 < fuzzable.patch
WORKDIR build-slow
RUN cmake .. -DGMX_BUILD_OWN_FFTW=ON -DBUILD_SHARED_LIBS=OFF -DGMX_PREFER_STATIC_LIBS=ON -DCMAKE_INSTALL_PREFIX=$(readlink -m ../out-slow/)
RUN AFL_USE_ASAN=1 make -j 16 | tee build.log 2>&1
RUN make install


FROM gromacs-build-run-common AS gromacs-run
COPY --from=afltriage-build /root/.cargo/bin/ /root/.cargo/bin/
COPY --from=crashwalk-build /root/go/ /root/go/
COPY --from=exploitable-build /root/exploitable /root/exploitable

WORKDIR /root/sci-apps-fuzz/src/
COPY common common
WORKDIR common
RUN ./setup-utils.sh

COPY --from=gromacs-build-slow /root/sci-apps-fuzz/build/gromacs /root/sci-apps-fuzz/build/gromacs/slow
COPY --from=gromacs-build-fast /root/sci-apps-fuzz/build/gromacs /root/sci-apps-fuzz/build/gromacs/fast
ENV BIN_SLOW=/root/sci-apps-fuzz/build/gromacs/slow/gromacs-2025.1/out-slow/bin/gmx
ENV BIN_FAST=/root/sci-apps-fuzz/build/gromacs/fast/gromacs-2025.1/out-fast/bin/gmx

WORKDIR /root/sci-apps-fuzz/src/
COPY targets/gromacs targets/gromacs
COPY justfile justfile

ENV GMX_MAXBACKUP=-1
ENV APP_NAME=gromacs
ENV KMP_AFFINITY=disabled
ENV OMP_NUM_THREADS=1
RUN cat common/fish_greeting >> /root/.config/fish/config.fish

CMD ["bash", "-c", "fish"]
