"""Start Mission Control.

    python3 run.py

Environment variables:
    MC_HOST     interface to bind (default 127.0.0.1)
    MC_PORT     port to listen on (default 8000; 0 picks a free port)
    MC_DB_PATH  SQLite file (default mission_control.db in the working directory)
"""
import os
import sys

from mission_control.server import create_server


def main():
    host = os.environ.get("MC_HOST", "127.0.0.1")
    port = int(os.environ.get("MC_PORT", "8000"))
    db_path = os.environ.get("MC_DB_PATH", "mission_control.db")
    server = create_server(host=host, port=port, db_path=db_path)
    actual_port = server.server_address[1]
    print("Mission Control listening on http://%s:%s/ (database %s)" % (host, actual_port, db_path))
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
