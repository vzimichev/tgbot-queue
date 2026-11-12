"""Create a stable ZIP from a Lambda dependency and source directory."""

import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def package(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            info = ZipInfo(path.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


if __name__ == "__main__":
    package(Path(sys.argv[1]), Path(sys.argv[2]))
