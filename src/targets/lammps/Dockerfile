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


FROM base AS lammps-build-run-common
RUN apt install -y bc cmake gfortran
COPY --from=harness-components-build /root/harness/build/lib/ /usr/lib/
COPY --from=just-dl /root/just/just /usr/local/bin/just
RUN make install


FROM lammps-build-run-common AS lammps-build
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
WORKDIR /root/sci-apps-fuzz/build/lammps
ARG LAMMPS_COMMIT=eab6e5d8420f1c55e72d92a2db47ed4f7a4adc68
ADD --checksum=$LAMMPS_COMMIT --keep-git-dir=true https://github.com/lammps/lammps.git#$LAMMPS_COMMIT lammps
WORKDIR lammps/


FROM lammps-build AS lammps-build-vanilla
RUN echo "/usr/lib/gcc/x86_64-linux-gnu/13" > /etc/ld.so.conf.d/gcc13.conf && ldconfig
WORKDIR /root/sci-apps-fuzz/build/lammps/lammps/build-vanilla
RUN cmake \
      -D CMAKE_C_COMPILER=/usr/bin/gcc \
      -D CMAKE_CXX_COMPILER=/usr/bin/g++ \
      -D PKG_MOLECULE=on \
      -D PKG_PYTHON=on \
      -D PKG_PHONON=on \
      -D PKG_KSPACE=on \
      -D PKG_MANYBODY=on \
      -D LAMMPS_EXCEPTIONS=on \
      -D BUILD_LIB=on \
      -D BUILD_SHARED_LIBS=on \
      -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX="/usr" \
      -D CMAKE_INSTALL_LIBDIR="lib" \
      -D CMAKE_INSTALL_LIBEXECDIR="/usr/lib" \
      -D BUILD_MPI=no \
      -D BUILD_OMP=no \
      -D BUILD_SHARED_LIBS=no \
      -D LAMMPS_MACHINE=serial \
      ../cmake && \
      cmake --build . -j16
RUN cp lmp_serial ../../lmp-vanilla


FROM lammps-build AS lammps-build-fast
COPY targets/lammps/fuzzable.patch /root/sci-apps-fuzz/build/lammps/
WORKDIR /root/sci-apps-fuzz/build/lammps/lammps
RUN patch --forward -p1 < ../fuzzable.patch
WORKDIR build-fast
RUN cmake \
      -D PKG_MOLECULE=on \
      -D PKG_PYTHON=on \
      -D PKG_PHONON=on \
      -D PKG_KSPACE=on \
      -D PKG_MANYBODY=on \
      -D LAMMPS_EXCEPTIONS=on \
      -D BUILD_LIB=on \
      -D BUILD_SHARED_LIBS=on \
      -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX="/usr" \
      -D CMAKE_INSTALL_LIBDIR="lib" \
      -D CMAKE_INSTALL_LIBEXECDIR="/usr/lib" \
      -D BUILD_MPI=no \
      -D BUILD_OMP=no \
      -D BUILD_SHARED_LIBS=no \
      -D LAMMPS_MACHINE=serial \
      ../cmake && \
      AFL_HARDEN=1 cmake --build . -j16
RUN cp lmp_serial ../lmp-fast


FROM lammps-build AS lammps-build-slow
COPY targets/lammps/fuzzable.patch /root/sci-apps-fuzz/build/lammps/
WORKDIR /root/sci-apps-fuzz/build/lammps/lammps
RUN patch --forward -p1 < ../fuzzable.patch
WORKDIR build-slow
RUN cmake \
      -D PKG_MOLECULE=on \
      -D PKG_PYTHON=on \
      -D PKG_PHONON=on \
      -D PKG_KSPACE=on \
      -D PKG_MANYBODY=on \
      -D LAMMPS_EXCEPTIONS=on \
      -D BUILD_LIB=on \
      -D BUILD_SHARED_LIBS=on \
      -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX="/usr" \
      -D CMAKE_INSTALL_LIBDIR="lib" \
      -D CMAKE_INSTALL_LIBEXECDIR="/usr/lib" \
      -D BUILD_MPI=no \
      -D BUILD_OMP=no \
      -D BUILD_SHARED_LIBS=no \
      -D LAMMPS_MACHINE=serial \
      ../cmake && \
      AFL_USE_ASAN=1 cmake --build . -j16
RUN cp lmp_serial ../lmp-slow


FROM lammps-build-run-common AS lammps-run
RUN echo "/usr/lib/gcc/x86_64-linux-gnu/13" > /etc/ld.so.conf.d/gcc13.conf && ldconfig
COPY --from=afltriage-build /root/.cargo/bin/ /root/.cargo/bin/
COPY --from=crashwalk-build /root/go/ /root/go/
COPY --from=exploitable-build /root/exploitable /root/exploitable

WORKDIR /root/sci-apps-fuzz/src/
COPY common common
WORKDIR common
RUN ./setup-utils.sh

COPY --from=lammps-build-slow /root/sci-apps-fuzz/build/lammps /root/sci-apps-fuzz/build/lammps/slow
COPY --from=lammps-build-fast /root/sci-apps-fuzz/build/lammps /root/sci-apps-fuzz/build/lammps/fast
COPY --from=lammps-build-vanilla /root/sci-apps-fuzz/build/lammps /root/sci-apps-fuzz/build/lammps/vanilla
ENV BIN_SLOW=/root/sci-apps-fuzz/build/lammps/slow/lammps/lmp-slow
ENV BIN_FAST=/root/sci-apps-fuzz/build/lammps/fast/lammps/lmp-fast
ENV BIN_VANILLA=/root/sci-apps-fuzz/build/lammps/vanilla/lammps/lmp-vanilla

WORKDIR /root/sci-apps-fuzz/src/
COPY targets/lammps targets/lammps
COPY justfile justfile

ENV APP_NAME=lammps
RUN cat common/fish_greeting >> /root/.config/fish/config.fish

CMD ["fish"]
