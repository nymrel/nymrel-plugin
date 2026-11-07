#!/usr/bin/env python3
"""Verify explicitly selected local Markdown citations without disclosing their contents."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

MAX_INPUT = 1024 * 1024
MAX_SOURCE = 2 * 1024 * 1024
ID = re.compile(r"[0-9a-f]{32}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class InvalidInput(Exception):
    pass


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise InvalidInput()
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in (".", "..") for p in value.split("/")) or str(path) != value:
        raise InvalidInput()
    if path.suffix.lower() != ".md":
        raise InvalidInput()
    return value


def read_source(root, relative):
    # Refuse symlinks at every component, even those pointing inside the root.
    current = root
    for part in relative.split("/"):
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise OSError("symlink")
    if not stat.S_ISREG(info.st_mode):
        raise OSError("not regular")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(current, flags)
    try:
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise OSError("not regular")
            data = stream.read(MAX_SOURCE + 1)
    except BaseException:
        # fdopen owns fd after success; an fdopen failure is exceptional.
        raise
    if len(data) > MAX_SOURCE:
        raise OSError("too large")
    return data


def verify(root, allowed, document):
    if not isinstance(document, dict) or set(document) != {"citations"}:
        raise InvalidInput()
    citations = document["citations"]
    if not isinstance(citations, list) or not 1 <= len(citations) <= 100:
        raise InvalidInput()
    seen = set()
    prepared = []
    for item in citations:
        if not isinstance(item, dict) or not {"id", "path", "sha256", "start", "end"} <= set(item) or set(item) - {"id", "path", "sha256", "start", "end", "quote"}:
            raise InvalidInput()
        ident, digest = item["id"], item["sha256"]
        path = relative_path(item["path"])
        start, end = item["start"], item["end"]
        if not isinstance(ident, str) or not ID.fullmatch(ident) or ident in seen or not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise InvalidInput()
        if type(start) is not int or type(end) is not int or start < 1 or end < start or end > 1000000:
            raise InvalidInput()
        if path not in allowed or ("quote" in item and (not isinstance(item["quote"], str) or not item["quote"] or len(item["quote"]) > 4096)):
            raise InvalidInput()
        seen.add(ident)
        prepared.append((item, path))
    results = []
    for item, path in prepared:
        status = "unresolved"
        try:
            data = read_source(root, path)
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                status = "changed"
            else:
                content = data.decode("utf-8", errors="strict")
                # LF and CRLF are line terminators; a final newline adds no line.
                lines = content.split("\n")
                if lines[-1] == "":
                    lines.pop()
                lines = [line[:-1] if line.endswith("\r") else line for line in lines]
                if item["end"] <= len(lines):
                    excerpt = "\n".join(lines[item["start"] - 1:item["end"]])
                    if "quote" not in item or item["quote"] in excerpt:
                        status = "verified"
        except (OSError, UnicodeError, ValueError):
            pass
        results.append({"id": item["id"], "status": status})
    return results


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid arguments; no citation results produced.\n")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Local source directory")
    parser.add_argument("--input", required=True, help="Private citation manifest JSON")
    parser.add_argument("--allow", action="append", required=True, help="Explicit root-relative Markdown path; repeat for each file")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root)
        if root.is_symlink() or not root.is_dir():
            raise InvalidInput()
        allowed = {relative_path(p) for p in args.allow}
        if len(allowed) > 100:
            raise InvalidInput()
        with open(args.input, "rb") as stream:
            raw = stream.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise InvalidInput()
        def unique_object(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise InvalidInput()
                obj[key] = value
            return obj
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        results = verify(root, allowed, document)
    except (InvalidInput, OSError, UnicodeError, ValueError, RecursionError):
        print("Invalid or unreadable input; no citation results produced.", file=sys.stderr)
        return 2
    print(json.dumps({"citations": results}, separators=(",", ":")))
    return 0 if all(r["status"] == "verified" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
