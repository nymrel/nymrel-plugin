#!/usr/bin/env python3
"""Check the retained source kit before a source-preview release; never rebuild it."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile

TAG_PATTERN = re.compile(r"workflow-starter-kit-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
KIT_PATH = Path("resources/workflow-starter-kit")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def verify_archive(root: Path, tag: str) -> tuple[Path, Path]:
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError("Use a workflow-starter-kit-vMAJOR.MINOR.PATCH tag")
    version = ".".join(match.groups())
    readme = root / KIT_PATH / "README.md"
    if not re.search(rf"^Version {re.escape(version)} ·", readme.read_text(encoding="utf-8"), re.M):
        raise ValueError("Tag version does not match the kit README")
    basename = f"nymrel-workflow-starter-kit-{version}"
    archive = root / "resources/releases" / f"{basename}.zip"
    checksum = archive.with_suffix(".zip.sha256")
    for path in (archive, checksum):
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("Release assets must be regular files, not symlinks")
    manifest = checksum.read_text(encoding="utf-8")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if manifest != f"{digest}  {archive.name}\n":
        raise ValueError("Release checksum or archive filename does not match")

    tracked = git(root, "ls-files", "-z", "--", str(KIT_PATH)).split("\0")
    expected = {f"{basename}/{Path(path).relative_to(KIT_PATH).as_posix()}": root / path
                for path in tracked if path}
    if not expected:
        raise ValueError("No tracked source kit files found")
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("Archive paths must exactly match the tracked source kit")
        for entry in entries:
            path = expected[entry.filename]
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError("Source kit entries must be regular files")
            if not stat.S_ISREG(entry.external_attr >> 16):
                raise ValueError("Archive entries must be regular files")
            source = path.read_bytes()
            if entry.file_size != len(source) or bundle.read(entry) != source:
                raise ValueError(f"Archive differs from source: {path.relative_to(root)}")
    return archive, checksum


def verify_source(root: Path, expected_sha: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("Expected source must be a full Git commit SHA")
    if git(root, "rev-parse", "HEAD") != expected_sha:
        raise ValueError("Checkout does not match the release source SHA")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Release checkout has tracked source changes")
    subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", expected_sha,
                    "refs/remotes/origin/main"], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-sha", help="Also require this exact source to be integrated in origin/main")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.expected_sha:
            verify_source(root, args.expected_sha)
        archive, checksum = verify_archive(root, args.tag)
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"Source release rejected: {exc}", file=sys.stderr)
        return 1
    print(f"Source archive verified: {archive.name} + {checksum.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
