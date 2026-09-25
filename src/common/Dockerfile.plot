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


FROM base AS plot-run
COPY --from=just-dl /root/just/just /usr/local/bin/just
WORKDIR /root/sci-apps-fuzz/src/
COPY common common
COPY justfile justfile

ENV APP_NAME=sciattack-plot

CMD ["fish"]
