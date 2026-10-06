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

mk() { d=/t/$1; mkdir -p $d/DEBIAN
  printf "Package: $1\nVersion: 1\nArchitecture: all\nMaintainer: a <a@b>\nDescription: t\n${2:+Depends: $2\n}" > $d/DEBIAN/control
  dpkg-deb -b $d /t/$1.deb >/dev/null; }
mk orphan-pre; mk dep-lib; mk emcomm-fake dep-lib
dpkg -i /t/orphan-pre.deb /t/dep-lib.deb /t/emcomm-fake.deb >/dev/null
apt-mark auto orphan-pre dep-lib >/dev/null; apt-mark manual emcomm-fake >/dev/null

echo "== (f) failing preview refuses and removes nothing"
mkdir /shim; printf "#!/bin/sh\nexit 1\n" > /shim/apt-mark; chmod +x /shim/apt-mark
rc=0; out=$(PATH=/shim:$PATH sh /src/bootstrap.sh --uninstall --yes 2>&1) || rc=$?
echo "$out" | tail -2; echo "rc=$rc"
[ "$rc" -ne 0 ] || fail "uninstall proceeded with a failing preview"
echo "$out" | grep -q "could not preview the removal; nothing was changed" || fail "no fail-closed message"
dpkg -s emcomm-fake >/dev/null 2>&1 || fail "emcomm-fake was removed"

echo "== (e) pre-existing orphan survives, new orphans go"
sh /src/bootstrap.sh --uninstall --yes 2>&1 | grep -E "^    |removed\."
dpkg -s emcomm-fake >/dev/null 2>&1 && fail "emcomm-fake still installed"
dpkg -s dep-lib >/dev/null 2>&1 && fail "newly orphaned dep-lib still installed"
dpkg -s orphan-pre >/dev/null 2>&1 || fail "pre-existing orphan was removed"
echo "== (g) package that becomes unneeded outside the confirmed list is not purged"
mk dep-lib2; mk emcomm-fake2 dep-lib2; mk bystander
dpkg -i /t/dep-lib2.deb /t/emcomm-fake2.deb /t/bystander.deb >/dev/null
apt-mark auto dep-lib2 >/dev/null; apt-mark manual emcomm-fake2 bystander >/dev/null
mkdir -p /shim
printf "#!/bin/sh\n/usr/bin/apt-get \"\$@\"; rc=\$?\n[ \"\$1\" = remove ] && apt-mark auto bystander >/dev/null\nexit \$rc\n" > /shim/apt-get
chmod +x /shim/apt-get; rm -f /shim/apt-mark
out=$(PATH=/shim:$PATH sh /src/bootstrap.sh --uninstall --yes 2>&1)
echo "$out" | grep -A2 "^warning"
echo "$out" | grep -q "^warning: these packages became unneeded" || fail "no warning"
dpkg -s bystander >/dev/null 2>&1 || fail "bystander was purged"
dpkg -s emcomm-fake2 >/dev/null 2>&1 && fail "emcomm-fake2 still installed"
dpkg -s dep-lib2 >/dev/null 2>&1 && fail "dep-lib2 still installed"
dpkg -s orphan-pre >/dev/null 2>&1 || fail "pre-existing orphan was removed"
echo "PASS"
'
