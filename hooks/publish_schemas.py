"""Publish `schemas/*.json` as site assets under `/schemas/`.

The generated schemas declare `$id: https://spindoxlabs.github.io/ds/schemas/<file>`,
so that URL has to serve the document itself — a producer pointing `$schema` at it
gets a 404 otherwise. The files stay in `schemas/` (generated from the Pydantic
models by `task -d libs/governance schema:generate`); this hook adds them to the
build without copying them into `docs/`, so there is still one source of truth and
nothing to keep in sync.

Registering them as MkDocs files rather than copying them post-build also means
link validation works: `docs/schemas/index.md` can link to a schema by relative
path and `mkdocs build --strict` fails if the name is wrong.
"""

from pathlib import Path

from mkdocs.structure.files import File

SCHEMA_DIR = "schemas"


def on_files(files, config):
    root = Path(config.config_file_path).parent
    src_dir = root / SCHEMA_DIR

    for path in sorted(src_dir.glob("*.json")):
        files.append(
            File(
                f"{SCHEMA_DIR}/{path.name}",
                src_dir=str(root),
                dest_dir=config["site_dir"],
                use_directory_urls=False,
            )
        )

    return files
