#!/bin/bash
set -euo pipefail
RELEASE_PATH="$1"
case "$RELEASE_PATH" in /opt/mop/releases/*) ;; *) exit 2;; esac
# Staging is private; code must be readable by both service users.
# Credentials remain separately protected under /etc/mop.
chown -R root:root "$RELEASE_PATH"
chmod -R a+rX "$RELEASE_PATH"
cd "$RELEASE_PATH/app"
npm ci --omit=dev --ignore-scripts --no-fund
for name in mop-settler.service mop-signer.service mop-backup@.service mop-backup@.timer; do
 install -m 0644 "$RELEASE_PATH/ops/settler/$name" "/etc/systemd/system/$name"
done
printf 'MOP_WORKER_CONFIG=/etc/mop/collector/config.json\n' > /etc/mop/backup-settler.env
printf 'MOP_SIGNER_CONFIG=/etc/mop/signer/config.json\n' > /etc/mop/backup-signer.env
chmod 644 /etc/mop/backup-*.env
systemctl stop mop-settler mop-signer 2>/dev/null || true
ln -sfn "$RELEASE_PATH" /opt/mop/current
systemctl daemon-reload
systemctl enable mop-signer mop-settler mop-backup@settler.timer mop-backup@signer.timer
systemctl start mop-signer mop-settler mop-backup@settler.timer mop-backup@signer.timer
systemctl is-active mop-signer mop-settler
# Check after startup, not merely systemd's initial "active" transition.
/usr/local/bin/node --input-type=module - <<'JS'
for (let i=0;i<15;i++) {
 await new Promise(r=>setTimeout(r,2000));
 try { const r=await fetch('http://127.0.0.1:4321/health'); const h=await r.json();
  if(h.chainId===11155111&&h.health.some(x=>x.name==='signer'&&x.ok))process.exit(0);
 } catch {}
}
console.error('Service did not become ready');process.exit(1);
JS
