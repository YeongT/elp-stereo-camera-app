# Windows release runbook

| Field | Value |
|---|---|
| Type | runbook |
| Audience | maintainers |
| Status | active |
| Source of truth | this document |
| Last reviewed | 2026-07-20 |

## Purpose

Build a Windows x64 distribution that runs without a separately installed
Python interpreter, then publish the same ZIP through the tag workflow.

## Preconditions

- Run the build on Windows x64; PyInstaller bundles the current platform only.
- Use the project-local environment and locked dependencies: `uv sync --group dev`.
- Keep `pyproject.toml`'s `project.version` and `elp_console.__version__` equal.
- Complete the camera smoke test on a target machine before publishing a tag.

## Inputs And Access

- Local build: project checkout and Windows camera hardware for the smoke test.
- GitHub release: permission to push an annotated `vX.Y.Z` tag; the workflow has
  repository `contents: write` permission to create the release.

## Procedure

1. Update both version declarations for the release, then verify them:

   ```powershell
   uv run python tools/check_version.py
   ```

2. Run the full test suite:

   ```powershell
   uv run pytest
   ```

3. Create the local Windows bundle:

   ```powershell
   .\tools\build_windows.ps1
   ```

   The output is `build/release/ELPStereoCamera-vX.Y.Z-win64.zip`. It contains
   an `ELPStereoCamera` folder; distribute and extract the complete folder,
   never the `.exe` by itself.

4. Extract the ZIP in a fresh folder, launch `ELPStereoCamera.exe`, and run
   the verification below.

5. After local verification, create and push the matching tag. This triggers
   `.github/workflows/windows-release.yml`, uploads a CI artifact, and creates
   the GitHub Release with the ZIP attached:

   ```powershell
   git tag -a vX.Y.Z -m "ELP Stereo Camera App vX.Y.Z"
   git push origin vX.Y.Z
   ```

## Verification

1. The extracted app opens with `ELP Stereo Camera App vX.Y.Z` in its title.
2. Start the selected camera, confirm the negotiated format and live preview.
3. Capture one snapshot to confirm `.runtime/captures` is writable beside the
   extraction directory's working folder.
4. Open Calibration and verify the existing calibration loads, or run a new
   capture/calibration cycle.
5. Confirm the GitHub action uploaded exactly one `*-win64.zip` artifact.

## Rollback

- Do not replace a published ZIP in place. Mark the GitHub Release as a
  pre-release or draft it, then publish a new higher version after the fix.
- Locally, remove only the specific failed archive under `build/release/` and
  rerun the build. Never delete the whole project or `.runtime` capture data.

## Failure Modes

| Symptom | Recovery |
|---|---|
| `PyInstaller` module missing | Run `uv sync --group dev` and retry. |
| Build has no `ELPStereoCamera.exe` | Stop; inspect PyInstaller output in `build/work/`. |
| App opens but camera backend fails | Reproduce with the project Python first, then include the failing backend/module in the spec's hidden imports. |
| Version/tag check fails | Make `pyproject.toml`, `elp_console.__version__`, and the tag match exactly. |

## Contacts Or Owners

Repository maintainers own version bumps, hardware verification, and release approval.

## Change History

- 2026-07-20: Added first PyInstaller Windows x64 packaging and tag-release workflow.
