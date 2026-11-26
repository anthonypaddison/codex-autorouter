# Release procedure

This fork preserves `vibeforge1111/Codex-Autorouter` as its upstream and publishes installable candidates from `anthonypaddison/Codex-Autorouter`. The commands below describe the planned v0.4.0-experimental.1 prerelease. For v1.0.0, follow [the stable release gates](STABLE_READINESS.md).

Do not create or push a tag until the candidate commit, real-host acceptance, and release evidence have been reviewed. Installing from a branch such as `main` is unsupported because a moving branch cannot identify the bytes that were reviewed.

## 1. Verify the exact candidate

Work from a clean checkout of the reviewed candidate branch. Confirm that `origin` is the fork and `upstream` is the original repository, then record the candidate commit:

```bash
git remote -v
git status --short
git rev-parse HEAD
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_release.py
(cd scripts && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_validate_release)
PYTHONDONTWRITEBYTECODE=1 python3 scripts/fuzz_router.py
```

Run the full CI-defined offline suite listed in README and review
[the release checklist](RELEASE_CHECKLIST.md). Label the candidate as an experimental release with its demonstrated
macOS CLI scope; other surfaces remain unverified until separately approved
acceptance. Configured-mode proof must use its exact allowlist, not a mandatory
legacy Sol/Astra probe. Health checks must never run paid probes. Do not infer
general classifier quality, entitlement or savings from one accepted child.
Enable and test GitHub private vulnerability reporting before public installation.
Review all reachable refs for secrets and deliberate author-identity exposure.

## 2. Create a local reviewed tag

After review approval, bind an annotated local tag to the recorded commit. Substitute the reviewed commit ID explicitly; do not tag an unverified moving `HEAD` by accident.

```bash
git tag -a v0.4.0-experimental.1 REVIEWED_COMMIT_ID -m "release v0.4.0-experimental.1"
git rev-list -n 1 v0.4.0-experimental.1
git show --no-patch --format=fuller v0.4.0-experimental.1
```

The resolved tag commit must exactly equal the reviewed candidate commit.

## 3. Build and checksum the archive

Create the release archive from the tag, not from the worktree. Keep the generated SHA256 checksum beside it:

```bash
mkdir -p dist
git archive --format=zip --prefix=Codex-Autorouter-v0.4.0-experimental.1/ -o dist/Codex-Autorouter-v0.4.0-experimental.1.zip v0.4.0-experimental.1
shasum -a 256 dist/Codex-Autorouter-v0.4.0-experimental.1.zip > dist/Codex-Autorouter-v0.4.0-experimental.1.zip.SHA256
shasum -a 256 -c dist/Codex-Autorouter-v0.4.0-experimental.1.zip.SHA256
unzip -l dist/Codex-Autorouter-v0.4.0-experimental.1.zip
```

Extract the archive into a fresh temporary directory. Use
`PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_release.py --archive`
from the extracted root with a build that includes archive validation. Run the
full test and host-acceptance gates against the extracted content. Record the tag
commit, archive SHA256, test results, host/build versions, and receipts. Compare
the released digest with a fresh archive produced from the same tag.

## 4. Publish only after the final gate

Pushing the tag makes the marketplace ref resolvable and is a separate, explicit release action:

```bash
git push origin refs/tags/v0.4.0-experimental.1
```

Attach the exact archive and its `.SHA256` file to the reviewed GitHub release. Keep the published `v0.3.0` pin intact. Any later code change requires a new version and a new review. Do not install, activate, publish, or merge as a side effect of validation.
