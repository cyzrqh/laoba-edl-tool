from __future__ import annotations

import multiprocessing as mp

from laoba.modern_gui import ModernLaobaApp


def main() -> None:
    mp.freeze_support()
    ModernLaobaApp().run()


if __name__ == "__main__":
    main()
