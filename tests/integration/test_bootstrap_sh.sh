#!/bin/sh
# Container integration test for bootstrap.sh key trust and uninstall preview.
# Run from the repo root:  sh tests/integration/test_bootstrap_sh.sh   (needs podman + network)
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
podman run --rm -v "$ROOT:/src:ro,z" docker.io/library/debian:13 sh -eu -c '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq gnupg curl ca-certificates >/dev/null
KEYRING=/usr/share/keyrings/emcomm-archive-keyring.asc
fail() { echo "FAIL: $*"; exit 1; }

mkdir -p /repo/testing /g && chmod 700 /g
GNUPGHOME=/g gpg --batch --passphrase "" --quick-gen-key "evil <evil@example.invalid>" ed25519 sign 0 2>/dev/null
GNUPGHOME=/g gpg --batch --armor --export evil@example.invalid > /evil.asc

echo "== (a) two-key attack"
cat /src/keys/emcomm-archive-keyring.asc /evil.asc > /repo/testing/emcomm-archive-keyring.asc
rc=0; out=$(sh /src/bootstrap.sh --repo-url file:///repo --channel testing --no-provision --yes 2>&1) || rc=$?
echo "$out" | tail -3; echo "rc=$rc"
[ "$rc" -ne 0 ] || fail "two-key file was accepted"
echo "$out" | grep -q "contains 2 keys" || fail "missing multiple-keys message"
[ ! -e $KEYRING ] || fail "keyring was installed"

echo "== (b) single real key"
cp /src/keys/emcomm-archive-keyring.asc /repo/testing/emcomm-archive-keyring.asc
rc=0; out=$(sh /src/bootstrap.sh --repo-url file:///repo --channel testing --no-provision --yes 2>&1) || rc=$?
echo "$out" | tail -4; echo "rc=$rc"
[ "$rc" -ne 0 ] || fail "expected a later apt failure"
echo "$out" | grep -Eq "contains [0-9]+ keys|does not match" && fail "failed at key check"
[ -s $KEYRING ] || fail "keyring not installed"
n=$(gpg --batch --show-keys --with-colons $KEYRING | grep -c "^pub:")
[ "$n" -eq 1 ] || fail "installed keyring has $n keys"

echo "== (c) rejects http and bad channel"
sh /src/bootstrap.sh --repo-url http://x --yes 2>&1 | grep -q "non-HTTPS" || fail "http accepted"
sh /src/bootstrap.sh --repo-url https://x --channel "a/b" --yes 2>&1 | grep -q "invalid channel" || fail "bad channel"

echo "== (d) uninstall preview, nothing installed"
rm -f $KEYRING /etc/apt/sources.list.d/emcomm.sources
sh /src/bootstrap.sh --uninstall --yes
echo "PASS"
'
