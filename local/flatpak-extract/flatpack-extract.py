#!/usr/bin/env python3
"""
flatpak-extract.py – Extract old and modern Flatpak bundles safely

Supports:
- Old-style bundles (OSTree)
- Modern bundles (tar, gzip, zstd)

Dependencies:
- ostree (for old-style)
- bsdtar or tar (for modern bundles)
"""

import os
import sys
import shutil
import subprocess
import tempfile
import argparse
from pathlib import Path

# ---------------------------
# Utility functions
# ---------------------------

def run_command(cmd, description="command"):
    """Run a shell command with pretty output."""
    print(f"⏳ {description}: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        return True
    except FileNotFoundError:
        print(f"[ERROR] Command not found: {cmd[0]}")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {description} failed with exit code {e.returncode}")
        return False

def check_dependency(cmd):
    """Check if a command is available."""
    return shutil.which(cmd) is not None

def detect_bundle_type(filepath: Path) -> str:
    """
    Try to detect Flatpak bundle type.
    Returns 'ostree' for old-style, 'tar' for modern bundle.
    """
    try:
        with open(filepath, 'rb') as f:
            head = f.read(16)
            if b'OSTREE' in head:
                return "ostree"
            elif head.startswith(b'\x1f\x8b'):  # gzip magic
                return "tar"
            elif head.startswith(b'\xfd7zXZ'):  # xz
                return "tar"
            elif head.startswith(b'BZh'):  # bzip2
                return "tar"
            elif head.startswith(b'\x28\xB5\x2F\xFD'):  # zstd magic
                return "tar"
            else:
                # fallback heuristic
                if filepath.suffix == '.flatpak':
                    return "ostree"
                else:
                    return "tar"
    except Exception as e:
        print(f"[WARN] Could not detect bundle type ({e}), assuming 'tar'")
        return "tar"

# ---------------------------
# Extraction handlers
# ---------------------------

def extract_ostree(flatpak_file: Path, outdir: Path):
    """Extract old-style OSTree flatpak."""
    if not check_dependency("ostree"):
        print("[ERROR] Missing dependency: ostree")
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="flatpak-ostree-") as tmpdir:
        repo = Path(tmpdir)
        print(f"[INFO] Using temporary OSTree repo: {repo}")

        if not run_command(["ostree", "init", f"--repo={repo}", "--mode=bare-user"], "Initialize OSTree repo"):
            return False
        if not run_command(["ostree", "static-delta", "apply-offline", f"--repo={repo}", str(flatpak_file)],
                           "Apply static delta"):
            return False

        # find commit hash
        commit_files = list(repo.rglob("*.commit"))
        if not commit_files:
            print("[ERROR] No commit file found.")
            return False

        commit = commit_files[0]
        commit_hash = commit.parent.name + commit.stem
        print(f"[INFO] Commit hash: {commit_hash}")

        if not run_command(["ostree", "checkout", f"--repo={repo}", "-U", commit_hash, str(outdir)],
                           "Checkout repository"):
            return False

        print(f"[SUCCESS] Files extracted to {outdir}")
        return True


def extract_tar(flatpak_file: Path, outdir: Path):
    """Extract tar-based flatpak (modern bundles)."""
    tar_cmd = None
    if check_dependency("bsdtar"):
        tar_cmd = "bsdtar"
    elif check_dependency("tar"):
        tar_cmd = "tar"
    else:
        print("[ERROR] Missing dependency: bsdtar or tar")
        sys.exit(1)

    if not outdir.exists():
        outdir.mkdir(parents=True)

    cmd = [tar_cmd, "-xf", str(flatpak_file), "-C", str(outdir)]
    return run_command(cmd, f"Extracting with {tar_cmd}")

# ---------------------------
# Main
# ---------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract .flatpak bundle (old or modern)"
    )
    parser.add_argument("filename", help="Path to the .flatpak file")
    parser.add_argument("--outdir", help="Output directory", default=None)

    args = parser.parse_args()
    file = Path(args.filename).resolve()

    if not file.exists():
        print(f"[ERROR] File not found: {file}")
        sys.exit(1)

    outdir = Path(args.outdir or f"{file.stem}-extract").resolve()
    if outdir.exists():
        print(f"[ERROR] Output directory already exists: {outdir}")
        sys.exit(1)

    bundle_type = detect_bundle_type(file)
    print(f"[INFO] Detected Flatpak type: {bundle_type}")

    if bundle_type == "ostree":
        success = extract_ostree(file, outdir)
    else:
        success = extract_tar(file, outdir)

    if success:
        print(f"\n✅ Extraction completed successfully!")
        print(f"📂 Output directory: {outdir}")
    else:
        print(f"\n❌ Extraction failed.")


if __name__ == "__main__":
    main()
