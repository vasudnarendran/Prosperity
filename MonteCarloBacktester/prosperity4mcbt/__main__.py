import sys
from pathlib import Path
from typing import Annotated, Optional

from typer import Argument, Option, Typer

from prosperity4mcbt.monte_carlo import default_dashboard_path, normalize_dashboard_path, run_monte_carlo_mode
from prosperity4mcbt.open import open_dashboard
from prosperity4mcbt.release_check import build_self_test_report, format_update_notice, get_release_status
from prosperity4mcbt.version import current_version

# Leaderboard settings — the Rust binary handles submission with embedded credentials
LEADERBOARD_SEED = 20260401
LEADERBOARD_SESSIONS = 1000
LEADERBOARD_SAMPLE_SESSIONS = 10
LEADERBOARD_FV_MODE = "simulate"
LEADERBOARD_TRADE_MODE = "simulate"
LEADERBOARD_TOMATO_SUPPORT = "quarter"


def version_callback(value: bool) -> None:
    if value:
        print(f"prosperity4mcbt {current_version()}")
        raise SystemExit(0)


app = Typer(context_settings={"help_option_names": ["--help", "-h"]})


@app.command()
def cli(
    algorithm: Annotated[
        Optional[Path],
        Argument(
            help="Path to the Python file containing the strategy to simulate.",
            show_default=False,
            resolve_path=True,
        ),
    ] = None,
    vis: Annotated[bool, Option("--vis", help="Open the Monte Carlo dashboard in the local visualizer when done.")] = False,
    out: Annotated[
        Optional[Path],
        Option(
            help="Path to dashboard JSON file (defaults to backtests/<timestamp>_monte_carlo/dashboard.json).",
            show_default=False,
            resolve_path=True,
        ),
    ] = None,
    no_out: Annotated[bool, Option("--no-out", help="Skip saving dashboard output.")] = False,
    data: Annotated[
        Optional[Path],
        Option(
            help="Path to data directory. If it contains round0/, that round0 directory is used as the actual calibration source.",
            show_default=False,
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
    quick: Annotated[
        bool,
        Option("--quick", help="Preset for a fast run: 100 sessions and 10 sample sessions."),
    ] = False,
    heavy: Annotated[
        bool,
        Option("--heavy", help="Preset for a full run: 1000 sessions and 100 sample sessions."),
    ] = False,
    sessions: Annotated[int, Option("--sessions", help="Number of Monte Carlo sessions to run.")] = 100,
    fv_mode: Annotated[str, Option("--fv-mode", help="Fair-value mode for the Rust simulator.")] = "simulate",
    trade_mode: Annotated[str, Option("--trade-mode", help="Trade-arrival mode for the Rust simulator.")] = "simulate",
    tomato_support: Annotated[str, Option("--tomato-support", help="Latent fair support for tomatoes in simulate mode.")] = "quarter",
    seed: Annotated[int, Option("--seed", help="RNG seed for the Rust simulator.")] = 20260401,
    python_bin: Annotated[
        str,
        Option("--python-bin", help="Python interpreter used for the strategy worker process."),
    ] = sys.executable,
    sample_sessions: Annotated[
        int,
        Option("--sample-sessions", help="Number of sessions to persist with full path/trace data for dashboard charts."),
    ] = 10,
    leaderboard_run: Annotated[
        bool,
        Option("--leaderboard-run", help="Run with locked leaderboard settings (1000 sessions, fixed seed) and submit score."),
    ] = False,
    display_name: Annotated[
        Optional[str],
        Option("--display-name", help="Display name for the leaderboard (optional)."),
    ] = None,
    self_test: Annotated[
        bool,
        Option("--self-test", help="Check the local install, Rust toolchain, and latest published release."),
    ] = False,
    no_update_check: Annotated[
        bool,
        Option("--no-update-check", help="Skip the automatic latest-release check before normal runs."),
    ] = False,
    version: Annotated[
        bool,
        Option("--version", "-v", help="Show the program's version number and exit.", is_eager=True, callback=version_callback),
    ] = False,
) -> None:
    if self_test:
        print(build_self_test_report(force_release_check=True))
        raise SystemExit(0)

    if no_out:
        print("Error: Monte Carlo mode always writes a dashboard bundle, so --no-out is not supported")
        raise SystemExit(1)
    if quick and heavy:
        print("Error: --quick and --heavy are mutually exclusive")
        raise SystemExit(1)
    if algorithm is None:
        print("Error: missing algorithm path. Pass a trader file or run with --self-test.")
        raise SystemExit(1)
    if not algorithm.exists():
        print(f"Error: algorithm file not found: {algorithm}")
        raise SystemExit(1)
    if not algorithm.is_file():
        print(f"Error: algorithm path is not a file: {algorithm}")
        raise SystemExit(1)

    if not no_update_check:
        notice = format_update_notice(get_release_status(force=False))
        if notice:
            print(notice)
            print()

    disable = None
    day = None
    leaderboard_submit = False

    if leaderboard_run:
        sessions = LEADERBOARD_SESSIONS
        sample_sessions = LEADERBOARD_SAMPLE_SESSIONS
        seed = LEADERBOARD_SEED
        fv_mode = LEADERBOARD_FV_MODE
        trade_mode = LEADERBOARD_TRADE_MODE
        tomato_support = LEADERBOARD_TOMATO_SUPPORT
        disable = "SQUID_INK,CROISSANTS,JAMS,DJEMBES,PICNIC_BASKET1,PICNIC_BASKET2"
        day = "-2"
        leaderboard_submit = True
        print(f"Leaderboard mode: {sessions} sessions, seed={seed}")
    elif quick:
        sessions = 100
        sample_sessions = 10
    elif heavy:
        sessions = 1000
        sample_sessions = 100

    dashboard_path = normalize_dashboard_path(out, False) or default_dashboard_path()

    dashboard = run_monte_carlo_mode(
        algorithm=algorithm,
        dashboard_path=dashboard_path,
        data_root=data,
        sessions=sessions,
        fv_mode=fv_mode,
        trade_mode=trade_mode,
        tomato_support=tomato_support,
        seed=seed,
        python_bin=python_bin,
        sample_sessions=sample_sessions,
        disable=disable,
        day=day,
        leaderboard_submit=leaderboard_submit,
        display_name=display_name,
    )

    total_stats = dashboard["overall"]["totalPnl"]
    print(f"Sessions: {int(total_stats['count'])}")
    print(f"Mean total PnL: {total_stats['mean']:,.2f}")
    print(f"Std total PnL: {total_stats['std']:,.2f}")
    print(f"Median total PnL: {total_stats['p50']:,.2f}")
    print(f"5%-95% range: {total_stats['p05']:,.2f} to {total_stats['p95']:,.2f}")
    print(f"Saved Monte Carlo dashboard to {dashboard_path}")

    if vis:
        open_dashboard(dashboard_path)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
