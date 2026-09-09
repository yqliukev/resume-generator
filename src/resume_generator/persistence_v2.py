"""Persistence utilities for SourceFile <-> GeneratedFile link records."""

from __future__ import annotations

import json
from pathlib import Path

from .models import (
	LinkLibrary,
	SourceFile,
	default_link_library_path,
)


def load_link_library(path: str) -> LinkLibrary:
	"""Load a link library JSON file from disk."""
	library_path = Path(path).expanduser().resolve(strict=False)
	with open(library_path, "r", encoding="utf-8") as handle:
		payload = json.load(handle)

	library = LinkLibrary.from_dict(payload)
	if library is None:
		raise ValueError(f"Invalid link library file: {library_path}")
	return library


def save_link_library(library: LinkLibrary, path: str | None = None) -> str:
	"""Persist a link library to JSON and return the written file path."""
	library_path = Path(path or default_link_library_path(library.source_path)).expanduser().resolve(strict=False)
	library_path.parent.mkdir(parents=True, exist_ok=True)

	payload = library.to_dict()
	tmp_path = str(library_path) + ".tmp"
	with open(tmp_path, "w", encoding="utf-8") as handle:
		json.dump(payload, handle, indent=2, ensure_ascii=True)
		handle.write("\n")

	Path(tmp_path).replace(library_path)
	return str(library_path)


def update_library_source_file(library: LinkLibrary, source_file: SourceFile) -> LinkLibrary:
	"""Replace the source file on a library and refresh linked outputs."""
	library.update_source_file(source_file)
	library.refresh_generated_files()
	return library
