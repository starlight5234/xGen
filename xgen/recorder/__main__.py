"""
CLI Transport for xGen Recorder.
Entry point for headless recording, listing, inspection, export, and replay via command line:
  python -m xgen.recorder record --name "My Flow"
  python -m xgen.recorder list
  python -m xgen.recorder show <id>
  python -m xgen.recorder export <id> --exporter action_xpath_json
  python -m xgen.recorder replay <id_or_file> --appium-url http://127.0.0.1:4723
Zero Qt dependencies.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from xgen.recorder.composition import create_recorder
from xgen.recorder.options import PlaybackOptions, RecordingOptions
from xgen.recorder.playback import PlaybackRunner, load_actions_from_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("xgen.recorder.cli")


def cmd_record(args: argparse.Namespace) -> int:
    service = create_recorder(storage_dir=args.storage_dir)
    opts = RecordingOptions(name=args.name, dialect_key=args.dialect)

    print(f"\n=======================================================")
    print(f" starting xGen Recording: '{args.name}'")
    print(f" Press Ctrl+C or Enter to stop recording...")
    print(f"=======================================================\n")

    rec_id = service.start(opts)
    print(f"Session started with ID: {rec_id}")

    try:
        if args.duration and args.duration > 0:
            print(f"Recording for {args.duration} seconds...")
            time.sleep(args.duration)
        else:
            # Wait for Enter or interrupt
            try:
                input()
            except EOFError:
                while True:
                    time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping recording...")

    meta = service.stop()
    print(f"\nRecording stopped successfully!")
    print(f"  ID:       {meta.id}")
    print(f"  Name:     {meta.name}")
    print(f"  Steps:    {meta.step_count}")
    print(f"  Duration: {meta.duration_seconds}s")
    print(f"  Saved in: {service.store.root_dir / meta.id}\n")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    service = create_recorder(storage_dir=args.storage_dir)
    recordings = service.list_recordings()

    if not recordings:
        print("No recordings found.")
        return 0

    print(f"\n{'ID':<38} {'NAME':<25} {'STEPS':<8} {'DURATION':<10} {'STARTED AT':<25}")
    print("-" * 110)
    for r in recordings:
        print(f"{r.id:<38} {r.name[:24]:<25} {r.step_count:<8} {f'{r.duration_seconds}s':<10} {r.started_at:<25}")
    print("")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    service = create_recorder(storage_dir=args.storage_dir)
    try:
        rec = service.get_recording(args.recording_id)
    except KeyError:
        print(f"Error: Recording session '{args.recording_id}' not found.", file=sys.stderr)
        return 1

    print(f"\nRecording: {rec.meta.name} ({rec.meta.id})")
    print(f"Started: {rec.meta.started_at} | Steps: {len(rec.steps)} | Duration: {rec.meta.duration_seconds}s\n")

    if not rec.steps:
        print("No steps recorded in this session.")
        return 0

    print(f"{'SEQ':<5} {'ACTION':<14} {'XPATH / TARGET':<50} {'WINDOW':<20}")
    print("-" * 95)
    for s in rec.steps:
        arr = s.to_action_array()
        action = arr[0]
        xpath = arr[1] if len(arr) > 1 else ""
        win_title = s.window.title[:18] if s.window else ""
        print(f"{s.seq:<5} {action:<14} {xpath[:48]:<50} {win_title:<20}")
    print("")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    service = create_recorder(storage_dir=args.storage_dir)
    try:
        result = service.export(args.recording_id, exporter_id=args.exporter)
    except Exception as e:
        print(f"Export error: {e}", file=sys.stderr)
        return 1

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result.text)
        print(f"Exported {result.filename} to {out_path}")
    else:
        print(result.text)

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):", file=sys.stderr)
        for w in result.warnings:
            print(f"  - {w}", file=sys.stderr)

    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    target = args.target
    actions_map = None

    # Check if target is a JSON file on disk
    if os.path.exists(target):
        try:
            actions_map = load_actions_from_file(target)
        except Exception as e:
            print(f"Error loading actions JSON file: {e}", file=sys.stderr)
            return 1
    else:
        # Load from recorded session via action_xpath_json exporter
        service = create_recorder(storage_dir=args.storage_dir)
        try:
            res = service.export(target, exporter_id="action_xpath_json")
            actions_map = json.loads(res.text)
        except Exception as e:
            print(f"Error resolving recording session '{target}': {e}", file=sys.stderr)
            return 1

    print(f"\n=======================================================")
    print(f" replaying {len(actions_map)} steps against Appium")
    print(f" URL: {args.appium_url}")
    print(f"=======================================================\n")

    # Connect to Appium / WinAppDriver
    try:
        from appium import webdriver
        from appium.options.windows import WindowsOptions
        options = WindowsOptions()
        if args.app_path:
            options.set_capability("app", args.app_path)
        else:
            options.set_capability("app", "Root")

        driver = webdriver.Remote(args.appium_url, options=options)
    except Exception as e:
        print(f"Failed to connect to Appium at {args.appium_url}: {e}", file=sys.stderr)
        print("Ensure Appium / WinAppDriver is running on port 4723.", file=sys.stderr)
        return 1

    playback_opts = PlaybackOptions(
        explicit_wait_seconds=args.timeout,
        action_delay_seconds=args.delay,
        continue_on_failure=args.continue_on_failure
    )
    runner = PlaybackRunner(driver, playback_opts)

    def on_progress(seq: int, action: str, success: bool):
        status_str = "OK" if success else "FAILED"
        print(f"Step {seq:<3} {action:<14} [{status_str}]")

    try:
        result = runner.run(actions_map, on_step_progress=on_progress)
        print(f"\nPlayback Finished: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"Steps executed: {result.executed_steps}/{result.total_steps}")
        if result.error_message:
            print(f"Error at step {result.failed_step}: {result.error_message}")
        return 0 if result.success else 1
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="xGen Automation Recorder CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Record
    p_rec = subparsers.add_parser("record", help="Start an interaction recording session")
    p_rec.add_argument("--name", default="Recorded_Session", help="Name of the session")
    p_rec.add_argument("--dialect", default="windows", help="Driver dialect (windows, mac2)")
    p_rec.add_argument("--duration", type=int, default=0, help="Record duration in seconds")
    p_rec.add_argument("--storage-dir", default=None, help="Custom storage root directory")

    # List
    p_list = subparsers.add_parser("list", help="List saved recordings")
    p_list.add_argument("--storage-dir", default=None, help="Custom storage root directory")

    # Show
    p_show = subparsers.add_parser("show", help="Display recorded steps in a session")
    p_show.add_argument("recording_id", help="Session ID")
    p_show.add_argument("--storage-dir", default=None, help="Custom storage root directory")

    # Export
    p_exp = subparsers.add_parser("export", help="Export recording to external format")
    p_exp.add_argument("recording_id", help="Session ID")
    p_exp.add_argument("--exporter", default="action_xpath_json", help="Exporter ID (action_xpath_json, raw_json, pytest_appium)")
    p_exp.add_argument("--output", "-o", default=None, help="Output file path")
    p_exp.add_argument("--storage-dir", default=None, help="Custom storage root directory")

    # Replay
    p_rep = subparsers.add_parser("replay", help="Replay recorded actions against Appium")
    p_rep.add_argument("target", help="Session ID or path to action_xpath_json file")
    p_rep.add_argument("--appium-url", default="http://127.0.0.1:4723", help="Appium server URL")
    p_rep.add_argument("--app-path", default=None, help="Target application executable path")
    p_rep.add_argument("--delay", type=float, default=0.5, help="Delay between actions in seconds")
    p_rep.add_argument("--timeout", type=float, default=10.0, help="Explicit wait timeout in seconds")
    p_rep.add_argument("--continue-on-failure", action="store_true", help="Continue executing on step failure")
    p_rep.add_argument("--storage-dir", default=None, help="Custom storage root directory")

    args = parser.parse_args()

    if args.command == "record":
        return cmd_record(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "show":
        return cmd_show(args)
    elif args.command == "export":
        return cmd_export(args)
    elif args.command == "replay":
        return cmd_replay(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
