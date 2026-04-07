import webbrowser
from pathlib import Path

from prosperity4mcbt.dashboard_server import ensure_dashboard_server, DEFAULT_PORT


def open_dashboard(output_file: Path) -> None:
    ensure_dashboard_server(output_file.parent)
    webbrowser.open(f"http://localhost:{DEFAULT_PORT}/")
