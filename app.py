from __future__ import annotations

import multiprocessing as mp

from laoba.gui import LaobaApp


def main() -> None:
    mp.freeze_support()
    LaobaApp().run()


if __name__ == "__main__":
    main()
