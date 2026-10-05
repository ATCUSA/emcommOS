#!/usr/bin/env bash
# Index and sign the channel tree mounted at /repo. Runs in debian:13 with the
# signing key mounted at /keys/signing.asc and its passphrase at /keys/passphrase.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends apt-utils createrepo-c rpm gnupg ca-certificates >/dev/null

GNUPGHOME=$(mktemp -d)
export GNUPGHOME
chmod 700 "$GNUPGHOME"
echo allow-loopback-pinentry > "$GNUPGHOME/gpg-agent.conf"
gpg --batch --quiet --pinentry-mode loopback --passphrase-file /keys/passphrase \
    --import /keys/signing.asc
# Select the signing-capable secret subkey explicitly (the primary is certify-only
# and may be a stub); the trailing "!" forces gpg to use exactly that key.
KEYID=$(gpg --batch --list-secret-keys --with-colons | awk -F: '
  $1 == "ssb" && $12 ~ /s/ {want = 1; next}
  $1 == "ssb" || $1 == "sec" {want = 0}
  want && $1 == "fpr" {print $10 "!"; exit}')
[ -n "$KEYID" ] || { echo "no signing subkey found in /keys/signing.asc" >&2; exit 1; }
SIGN=(gpg --batch --yes --pinentry-mode loopback --passphrase-file /keys/passphrase
      --local-user "$KEYID")

cd /repo

for suite in $DEB_SUITES; do
  dist=deb/dists/$suite
  for arch in amd64 arm64; do
    mkdir -p "$dist/main/binary-$arch"
    (cd deb && apt-ftparchive --arch "$arch" packages "pool/$suite") > "$dist/main/binary-$arch/Packages"
    gzip -9kf "$dist/main/binary-$arch/Packages"
  done
  rm -f "$dist/Release" "$dist/InRelease" "$dist/Release.gpg"
  release_tmp=$(mktemp)
  apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=emcommOS \
    -o APT::FTPArchive::Release::Label=emcommOS \
    -o "APT::FTPArchive::Release::Suite=$suite" \
    -o "APT::FTPArchive::Release::Codename=$suite" \
    -o "APT::FTPArchive::Release::Architectures=amd64 arm64" \
    -o APT::FTPArchive::Release::Components=main \
    release "$dist" > "$release_tmp"
  mv "$release_tmp" "$dist/Release"
  chmod 644 "$dist/Release"
  "${SIGN[@]}" --clearsign -o "$dist/InRelease" "$dist/Release"
  "${SIGN[@]}" --armor --detach-sign -o "$dist/Release.gpg" "$dist/Release"
done

cat > "$HOME/.rpmmacros" <<EOM
%_gpg_name $KEYID
%_gpg_path $GNUPGHOME
%_gpg_sign_cmd_extra_args --batch --pinentry-mode loopback --passphrase-file /keys/passphrase
EOM
for rpm_file in $NEW_RPMS; do
  rpmsign --addsign "$rpm_file" >/dev/null
done
for dir in $RPM_DIRS; do
  createrepo_c --quiet --update "$dir"
  "${SIGN[@]}" --armor --detach-sign -o "$dir/repodata/repomd.xml.asc" "$dir/repodata/repomd.xml"
done
echo "publish OK"
