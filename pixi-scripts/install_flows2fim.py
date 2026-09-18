"""Ensure the flows2fim binary is installed in the active pixi environment.

flows2fim is not a conda/pypi package, so it cannot be a locked pixi dependency. Instead
this installs it into the environment prefix ($CONDA_PREFIX/Library/bin, which is on PATH),
so the bare `flows2fim` command works. It is idempotent and runs automatically via the
pixi activation script (see pixi.toml), so no manual step is needed.
"""

import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "v0.5.0"
URL = f"https://github.com/NGWPC/flows2fim/releases/download/{VERSION}/flows2fim-windows-amd64.zip"


def main() -> None:
    prefix = os.environ.get("CONDA_PREFIX")
    if not prefix:
        sys.exit("CONDA_PREFIX not set; run this via `pixi run`.")

    # Activation calls this on every `pixi run`, so the common path is a fast no-op.
    # To pick up a new VERSION above, delete the environment and reinstall it.
    target = Path(prefix) / "Library" / "bin" / "flows2fim.exe"
    if target.exists():
        return  # already installed in this environment

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Installing flows2fim {VERSION} into {target.parent}")
    data = urllib.request.urlopen(URL).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = [m for m in z.namelist() if m.endswith("flows2fim.exe")]
        if not members:
            sys.exit(f"flows2fim.exe not found in {URL}")
        with z.open(members[0]) as src, open(target, "wb") as dst:
            dst.write(src.read())
    print(f"Installed flows2fim -> {target}")


if __name__ == "__main__":
    main()
