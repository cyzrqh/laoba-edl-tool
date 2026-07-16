from __future__ import annotations

import os
import sys
import traceback
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any


class PipeWriter:
    def __init__(self, connection: Connection, stream_name: str):
        self.connection = connection
        self.stream_name = stream_name
        self._buffer = ""
        self.encoding = "utf-8"

    @property
    def buffer(self):
        return self

    @property
    def closed(self) -> bool:
        return False

    def write(self, value: Any) -> int:
        if isinstance(value, (bytes, bytearray)):
            text = bytes(value).decode("utf-8", errors="replace")
        else:
            text = str(value)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._send(line + "\n")
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._send(self._buffer)
            self._buffer = ""

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError("PipeWriter 没有真实文件描述符")

    def _send(self, text: str) -> None:
        try:
            self.connection.send(("log", self.stream_name, text))
        except (BrokenPipeError, EOFError, OSError):
            pass


def run_edl_backend(connection: Connection, args: list[str], cwd: str) -> None:
    """Multiprocessing target that runs upstream edlclient with captured output."""
    stdout = PipeWriter(connection, "stdout")
    stderr = PipeWriter(connection, "stderr")
    old_stdout, old_stderr, old_argv = sys.stdout, sys.stderr, sys.argv[:]
    old_cwd = os.getcwd()
    rc = 1
    try:
        sys.stdout = stdout
        sys.stderr = stderr
        sys.argv = ["edl", *args]
        Path(cwd).mkdir(parents=True, exist_ok=True)
        os.chdir(cwd)
        # edlclient.edl parses sys.argv at import time.  Import only after argv is set.
        import edlclient.edl as edl_module

        # Upstream's module-level run() currently discards main.run()'s return value.
        # Instantiate the CLI class directly so failures are reported correctly.
        cli = edl_module.main(edl_module.args, edl_module.__name__)
        result = cli.run()
        rc = int(result) if isinstance(result, int) else 0
    except SystemExit as exc:
        rc = int(exc.code) if isinstance(exc.code, int) else 0
    except BaseException:
        traceback.print_exc(file=stderr)
        rc = 1
    finally:
        stdout.flush()
        stderr.flush()
        try:
            connection.send(("exit", rc))
        except (BrokenPipeError, EOFError, OSError):
            pass
        connection.close()
        os.chdir(old_cwd)
        sys.stdout, sys.stderr, sys.argv = old_stdout, old_stderr, old_argv
