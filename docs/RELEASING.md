# Release procedure

This fork preserves `vibeforge1111/Codex-Autorouter` as its upstream and publishes installable candidates from `anthonypaddison/Codex-Autorouter`. The marketplace metadata intentionally names the future immutable ref `v0.3.0`; editing that metadata does not create, publish, or validate the tag.

Do not create or push a tag until the candidate commit, real-host acceptance, and release evidence have been reviewed. Installing from a branch such as `main` is unsupported because a moving branch cannot identify the bytes that were reviewed.

## 1. Verify the exact candidate

Work from a clean checkout of the reviewed candidate branch. Confirm that `origin` is the fork and `upstream` is the original repository, then record the candidate commit:

```bash
git remote -v
git status --short
git rev-parse HEAD
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_release.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v scripts.test_validate_release
PYTHONDONTWRITEBYTECODE=1 python3 scripts/fuzz_router.py
```

Run the full repository-defined test suite and complete the real Desktop/CLI acceptance evidence before continuing. The health check must not run an automatic paid probe; readiness capability must come from a genuine successful GPT-6 Sol or Astra escalation during controlled acceptance or normal work. Astra acceptance is a separately bounded frontier check, not part of routine release probing.

## 2. Create a local reviewed tag

After review approval, bind an annotated local tag to the recorded commit. Substitute the reviewed commit ID explicitly; do not tag an unverified moving `HEAD` by accident.

```bash
git tag -a v0.3.0 REVIEWED_COMMIT_ID -m "release v0.3.0"
git rev-list -n 1 v0.3.0
git show --no-patch --format=fuller v0.3.0
```

The resolved tag commit must exactly equal the reviewed candidate commit.

## 3. Build and checksum the archive

Create the release archive from the tag, not from the worktree. Keep the generated SHA256 checksum beside it:

```bash
mkdir -p dist
git archive --format=zip --prefix=Codex-Autorouter-v0.3.0/ -o dist/Codex-Autorouter-v0.3.0.zip v0.3.0
shasum -a 256 dist/Codex-Autorouter-v0.3.0.zip > dist/Codex-Autorouter-v0.3.0.zip.SHA256
shasum -a 256 -c dist/Codex-Autorouter-v0.3.0.zip.SHA256
unzip -l dist/Codex-Autorouter-v0.3.0.zip
```

Extract the archive into a fresh temporary directory and rerun `scripts/validate_release.py` plus the full test and host-acceptance gates against the extracted content. Record the tag commit, archive SHA256, test results, host/build versions, and receipt evidence in the release evidence.

## 4. Publish only after the final gate

Pushing the tag makes the marketplace ref resolvable and is a separate, explicit release action:

```bash
git push origin refs/tags/v0.3.0
```

Attach the exact archive and its `.SHA256` file to the reviewed GitHub release. Do not retag `v0.3.0`; any later code change requires a new version and a new review. Do not install, activate, publish, or merge as a side effect of validation.
