from __future__ import annotations

import multiprocessing as mp

from laoba.engine_cli import main


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
