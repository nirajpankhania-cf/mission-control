"""Start Mission Control.

    python3 run.py

Environment variables:
    MC_HOST            interface to bind (default 127.0.0.1)
    MC_PORT            port to listen on (default 8000; 0 picks a free port)
    MC_DB_PATH         SQLite file (default mission_control.db in the working directory)
    ANTHROPIC_API_KEY  when set, model steps call the Anthropic API; when absent
                       the deterministic fake is used and the console says so
    MC_FAST_MODEL      model for sorting and checks (default in mission_control/config.py)
    MC_STRONG_MODEL    model for draft and review
"""
import os
import sys

from mission_control import config
from mission_control.server import choose_client, create_server


def main():
    host = os.environ.get("MC_HOST", "127.0.0.1")
    port = int(os.environ.get("MC_PORT", "8000"))
    db_path = os.environ.get("MC_DB_PATH", "mission_control.db")
    client = choose_client()
    server = create_server(host=host, port=port, db_path=db_path, client=client)
    actual_port = server.server_address[1]
    print("Mission Control listening on http://%s:%s/ (database %s)" % (host, actual_port, db_path))
    if client.name == "fake":
        print("Model steps are SIMULATED: ANTHROPIC_API_KEY is not set, using the built-in fake model.")
    else:
        print("Model steps are LIVE: fast model %s, strong model %s." % (config.fast_model(), config.strong_model()))
    print("Engineer form: http://%s:%s/   Flight Director console: http://%s:%s/console" % (host, actual_port, host, actual_port))
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
