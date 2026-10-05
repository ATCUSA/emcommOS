# Maintainer setup

One-time setup for package signing, hosting, and CI. Use a dedicated project key,
not anyone's personal identity.

## 1. Project signing key

Do this on a trusted machine. The primary key is certify-only and stays offline;
only the signing subkey goes to CI.

```bash
export GNUPGHOME="$HOME/.gnupg-emcomm"   # dedicated keyring
mkdir -m 700 -p "$GNUPGHOME"
gpg --quick-gen-key "emcommOS Package Signing" ed25519 cert 3y
FPR=$(gpg --list-keys --with-colons "emcommOS Package Signing" | awk -F: '/^fpr/ {print $10; exit}')
gpg --quick-add-key "$FPR" ed25519 sign 3y
mkdir -p keys
gpg --armor --export "$FPR" > keys/emcomm-archive-keyring.asc
echo "$FPR" > keys/fingerprint.txt
gpg --armor --export-secret-subkeys "$FPR" > "$GNUPGHOME/ci-signing-subkey.asc"
```

- Store an encrypted offline backup of `gpg --armor --export-secret-keys "$FPR"` and of
  `$GNUPGHOME/openpgp-revocs.d/$FPR.rev` (the revocation certificate).
- Never commit secret material. Commit only `keys/emcomm-archive-keyring.asc` and
  `keys/fingerprint.txt`.
- Renew before expiry with `gpg --quick-set-expire "$FPR" 3y` and `gpg --quick-set-expire "$FPR" 3y '*'`,
  then re-export the public key and commit it.

## 2. Cloudflare R2

1. Create a bucket (for example `emcomm-repo`).
2. Enable public read access through an r2.dev URL or a custom domain. That public base URL,
   with no trailing slash, is `EMCOMM_REPO_URL`.
3. Prefer a custom domain over the rate-limited r2.dev URL before volunteers bootstrap from the repository.
4. Create an R2 API token with Object Read & Write scoped to the bucket. Note the access key ID,
   the secret, and your account ID.

## 3. GitHub repository settings

Secrets (Settings → Secrets and variables → Actions → Secrets):

| Name | Value |
|---|---|
| `EMCOMM_SIGNING_KEY` | contents of `ci-signing-subkey.asc` (then delete that file) |
| `EMCOMM_SIGNING_PASSPHRASE` | the key passphrase (empty if none) |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | R2 token |
| `R2_ACCOUNT_ID` | Cloudflare account ID |

Variables:

| Name | Value |
|---|---|
| `EMCOMM_REPO_URL` | public bucket URL, e.g. `https://pub-xxxx.r2.dev` |
| `R2_BUCKET` | bucket name |

Also enable Settings → Actions → General → "Allow GitHub Actions to create and approve pull
requests" (used by `watch-upstream`). Arm64 builds use the free `ubuntu-24.04-arm` runners,
which are available to public repositories.
