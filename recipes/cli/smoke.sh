#!/usr/bin/env bash
set -euo pipefail
emcomm --help >/dev/null
emcomm radios | grep -q icom-ic7300
test -f /opt/emcomm/share/emcomm/ansible/ansible_collections/emcomm/station/playbooks/station.yml
test -s /opt/emcomm/share/emcomm/ansible/ansible_collections/emcomm/station/roles/base/files/emcomm-archive-keyring.asc
grep -q '^EMCOMM_KEY_FINGERPRINT="[0-9A-F]\{40\}"$' /opt/emcomm/share/emcomm/bootstrap.sh
ansible-playbook --version >/dev/null
