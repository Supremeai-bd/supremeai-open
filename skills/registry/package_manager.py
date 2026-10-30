"""skills.sh-compatible CLI and importer engine.

Verbs: install (local dir, git url, or index name), list, remove, pack.
Registry sources resolve exclusively through registry/index.json — no
credentials, no hardcoded endpoints.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from .manifest_schema import ManifestError, parse_skill_md
from .progressive_loader import ProgressiveLoader

INDEX_FILENAME = "index.json"


class PackageManagerError(RuntimeError):
    """Raised when an install/remove/pack operation cannot proceed."""


class PackageManager:
    def __init__(self, target_root: Path, index_path: Path | None = None) -> None:
        self.target_root = Path(target_root)
        self.index_path = (
            Path(index_path) if index_path else self.target_root / INDEX_FILENAME
        )

    # ---- verbs -------------------------------------------------------
    def install(self, source: str) -> Path:
        """Install a skill from a local dir, a git url, or an index name."""
        staged = self._stage_source(source)
        try:
            if not (staged / "SKILL.md").is_file():
                raise PackageManagerError(
                    f"not a skill directory (no SKILL.md): {source}"
                )
            descriptor, _ = parse_skill_md(
                (staged / "SKILL.md").read_text(encoding="utf-8"),
                source_path=str(staged / "SKILL.md"),
            )
            destination = self.target_root / descriptor.name
            if destination.exists():
                raise PackageManagerError(f"skill already installed: {descriptor.name}")
            shutil.copytree(staged, destination)
            return destination
        finally:
            shutil.rmtree(staged, ignore_errors=True)

    def list_installed(self) -> list[str]:
        if not self.target_root.is_dir():
            return []
        names = []
        for skill_md in sorted(self.target_root.glob("*/SKILL.md")):
            names.append(skill_md.parent.name)
        return names

    def remove(self, name: str) -> Path:
        if not name or "/" in name or Path(name).name != name or name in (".", ".."):
            raise PackageManagerError(f"invalid skill name: {name!r}")
        destination = self.target_root / name
        if not destination.is_dir():
            raise PackageManagerError(f"skill not installed: {name}")
        shutil.rmtree(destination)
        return destination

    def pack(self, skill_dir: Path, output: Path | None = None) -> Path:
        """Build a distributable .skill tar.gz from a skill directory."""
        skill_dir = Path(skill_dir)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            raise PackageManagerError(
                f"not a skill directory (no SKILL.md): {skill_dir}"
            )
        name = skill_dir.name
        output = output or (skill_dir.parent / f"{name}.skill")
        with tarfile.open(output, "w:gz") as archive:
            for member in sorted(skill_dir.rglob("*")):
                archive.add(member, arcname=str(member.relative_to(skill_dir.parent)))
        return output

    # ---- staging -----------------------------------------------------
    def _stage_source(self, source: str) -> Path:
        staging = Path(tempfile.mkdtemp(prefix="skill-install-"))
        candidate = Path(source)
        if candidate.is_dir():
            shutil.copytree(candidate, staging / "skill")
            return staging / "skill"
        git_source, git_ref = self._resolve_index(source)
        if git_source is None:
            git_source, git_ref = source, None
        clone_cmd = ["git", "clone", "--depth", "1"]
        if git_ref:
            clone_cmd += ["--branch", git_ref]
        clone_cmd += [git_source, str(staging / "skill")]
        result = subprocess.run(
            clone_cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            shutil.rmtree(staging, ignore_errors=True)
            raise PackageManagerError(
                f"git clone failed for {source!r}: {result.stderr.strip()[:200]}"
            )
        return staging / "skill"

    def _resolve_index(self, name: str) -> tuple[str | None, str | None]:
        """Return (git_url, ref) for an index name, or (None, None).

        The ref is returned separately: ``url@ref`` is not valid git-clone
        syntax (it must be passed as ``--branch <ref>``).
        """
        if not self.index_path.is_file():
            return None, None
        skills = ProgressiveLoader.read_index(self.index_path)
        entry = skills.get(name)
        if entry is None:
            return None, None
        return str(entry["git"]), entry.get("ref") or None


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supremeai-skill", description="SupremeAI skill package manager"
    )
    parser.add_argument("--root", default=".", help="skill installation root")
    parser.add_argument("--index", default=None, help="path to registry index.json")
    verbs = parser.add_subparsers(dest="verb", required=True)
    install = verbs.add_parser("install")
    install.add_argument("source")
    verbs.add_parser("list")
    remove = verbs.add_parser("remove")
    remove.add_argument("name")
    pack = verbs.add_parser("pack")
    pack.add_argument("directory")
    pack.add_argument("--out", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    manager = PackageManager(Path(args.root), Path(args.index) if args.index else None)
    try:
        if args.verb == "install":
            print(f"installed: {manager.install(args.source)}")
        elif args.verb == "list":
            for name in manager.list_installed():
                print(name)
        elif args.verb == "remove":
            print(f"removed: {manager.remove(args.name)}")
        elif args.verb == "pack":
            print(
                f"packed: {manager.pack(Path(args.directory), Path(args.out) if args.out else None)}"
            )
    except (PackageManagerError, ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
