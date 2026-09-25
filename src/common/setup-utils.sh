#!/bin/bash
set -euxo pipefail

mv /usr/bin/perf /usr/bin/perf.script
ln -s /usr/lib/linux-tools/*/perf /usr/bin/perf

EXPL=$(readlink -e /root/exploitable/exploitable/exploitable.py) 

fish -c "fish_add_path /usr/local/go/bin"
echo 'export PATH="$PATH:/usr/local/go/bin"' >> ~/.bashrc
mkdir -p /root/go/bin/
fish -c "fish_add_path /root/go/bin"
echo 'export PATH="$PATH:/root/go/bin"' >> ~/.bashrc

mkdir -p /root/.cargo/bin/
fish -c "fish_add_path /root/.cargo/bin"
echo 'export PATH="$PATH:/root/.cargo/bin"' >> ~/.bashrc

echo "source $EXPL" >> ~/.gdbinit
echo "export CW_EXPLOITABLE=$EXPL" >> ~/.config/fish/config.fish
echo "export CW_EXPLOITABLE=$EXPL" >> ~/.bashrc
