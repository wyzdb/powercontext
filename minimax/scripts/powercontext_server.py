"""Start the PowerContext server from the installed package.

The official CLI (``powercontext server run``) needs the ``cli`` extra. The
submission only needs the server process, so this launcher mirrors the CLI's
own ``_run_configured_server`` path with the pinned package instead of pulling
in the interactive wizard dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from powercontext.server.configuration import server_settings_context
from powercontext.server.factory import create_server_app
from powercontext.server.logging import configure_server_logging
from powercontext.server.tracing import configure_server_tracing


def main() -> int:
    env_file = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    with server_settings_context(
        env_file=env_file,
        process_environment_overrides=True,
    ) as settings:
        configure_server_logging(settings.logging)
        tracing = configure_server_tracing(settings.tracing)
        try:
            application = create_server_app(settings=settings, tracing=tracing)
            uvicorn.run(
                application,
                host=settings.http.host,
                port=settings.http.port,
                access_log=False,
                log_config=None,
            )
        finally:
            tracing.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
