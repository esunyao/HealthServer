"""Digest the executable code and prompt assets that this process loads."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def _manifest_files(root: Path, *, suffixes: set[str] | None = None) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if suffixes is None or path.suffix.lower() in suffixes:
            yield path


def compute_artifact_sha256(module_root: Path | None = None, skills_root: Path | None = None) -> str:
    root = module_root or Path(__file__).resolve().parents[2]
    package_root = root / "src" / "nutriathena_agent"
    prompt_root = skills_root or root.parent / "AgentDeveloper" / "skills"
    if not package_root.is_dir() or not prompt_root.is_dir():
        raise RuntimeError("NutriAthenaAgent 代码或餐食规范资产缺失，无法计算部署摘要")

    manifest: list[tuple[str, Path]] = []
    manifest.extend(
        ("nutriathena_agent/" + path.relative_to(package_root).as_posix(), path)
        for path in _manifest_files(package_root, suffixes={".py"})
    )
    manifest.extend(
        ("migrations/" + path.relative_to(root / "migrations").as_posix(), path)
        for path in _manifest_files(root / "migrations", suffixes={".sql"})
    )
    manifest.extend(
        ("meal-skills/" + path.relative_to(prompt_root).as_posix(), path)
        for path in _manifest_files(prompt_root)
    )
    for name in ("pyproject.toml", "uv.lock"):
        path = root / name
        if path.is_file():
            manifest.append((name, path))

    digest = hashlib.sha256()
    for relative, path in sorted(manifest, key=lambda item: item[0]):
        encoded_name = relative.encode("utf-8")
        contents = path.read_bytes()
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(contents).to_bytes(8, "big"))
        digest.update(contents)
    return digest.hexdigest()
