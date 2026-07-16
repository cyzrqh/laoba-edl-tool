from __future__ import annotations

import sys
import traceback


def main() -> int:
    # edlclient.edl 会在导入时解析 sys.argv，因此必须延迟导入。
    try:
        import edlclient.edl as edl_module

        cli = edl_module.main(edl_module.args, edl_module.__name__)
        result = cli.run()
        return int(result) if isinstance(result, int) else 0
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 0
    except BaseException:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
