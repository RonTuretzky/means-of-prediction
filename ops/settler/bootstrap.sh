#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends ca-certificates curl xz-utils sqlite3 unattended-upgrades
TASK_NODE_DIR=$(mktemp -d)
cd "$TASK_NODE_DIR"
NODE_VERSION=v24.21.0
curl --fail --silent --show-error --location "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz" -o node.tar.xz
curl --fail --silent --show-error --location "https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt" -o SHASUMS256.txt
TASK_NODE_SHA=$(awk -v file="node-$NODE_VERSION-linux-x64.tar.xz" '$2 == file {print $1}' SHASUMS256.txt)
test ${#TASK_NODE_SHA} -eq 64
printf '%s  node.tar.xz\n' "$TASK_NODE_SHA" | sha256sum --check --status
tar -xJf node.tar.xz -C /usr/local --strip-components=1
cd /
rm -rf "$TASK_NODE_DIR"
groupadd --system mop-ipc
useradd --system --home /var/lib/mop-settler --shell /usr/sbin/nologin mop-settler
useradd --system --home /var/lib/mop-signer --shell /usr/sbin/nologin mop-signer
usermod -aG mop-ipc mop-settler
usermod -aG mop-ipc mop-signer
install -d -m 0755 /opt/mop/releases /etc/mop
install -d -o mop-settler -g mop-settler -m 0700 /etc/mop/collector /var/lib/mop-settler /var/lib/mop-settler/backups
install -d -o mop-signer -g mop-signer -m 0700 /etc/mop/signer /var/lib/mop-signer /var/lib/mop-signer/backups
# No mailbox, wallet or API credentials are present in provider user-data.
touch /opt/mop/bootstrap-complete
