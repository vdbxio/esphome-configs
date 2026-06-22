#!/usr/bin/env python3
# /// script
# dependencies = ["textual", "pyserial"]
# ///
"""
zloader - ESPHome firmware uploader and compiler TUI.

Drop-in script for ESPHome folders. Run: pipx run zloader.py

Or with venv: python3 -m venv .venv && source .venv/bin/activate && pip install textual pyserial && python zloader.py

Layout: Top bar (YAML dropdown, Compile, Upload), left device list, main output area.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual.message import Message
    from textual.widgets import Button, Footer, Label, ListItem, ListView, RichLog, Select, Static
except ImportError as e:
    print("Missing dependency. Install with: pip install textual pyserial", file=sys.stderr)
    sys.exit(1)

try:
    import serial.tools.list_ports
except ImportError as e:
    print("Missing pyserial. Install with: pip install pyserial", file=sys.stderr)
    sys.exit(1)

# Debounce: count disconnect only after device missing for N consecutive polls
DEBOUNCE_POLLS = 4
POLL_INTERVAL = 0.4  # seconds


def get_cu_usbmodem_devices() -> set[str]:
    """List cu.usbmodem* devices in /dev (macOS)."""
    devices = set()
    try:
        for name in os.listdir("/dev"):
            if name.startswith("cu.usbmodem"):
                devices.add(os.path.join("/dev", name))
    except (FileNotFoundError, PermissionError):
        pass
    return devices


def get_connected_boards() -> list[tuple[str, str]]:
    """Return list of (device_path, description) for ESP boards."""
    result = []
    for port in serial.tools.list_ports.comports():
        if "Bluetooth-Incoming-Port" in port.device or "debug-console" in port.device:
            continue
        if "CH340" in (port.description or "") or "CP210x" in (port.description or ""):
            result.append((port.device, port.description or "USB serial"))
        elif not re.search(r"(AMA|ACM|Bluetooth|IrDA)", port.device, re.IGNORECASE):
            result.append((port.device, port.description or "USB modem"))
    return result


def discover_yamls(config_dir: Path) -> list[tuple[str, str]]:
    """Return [(display_name, full_path), ...] for ESPHome config YAMLs."""
    excluded = {"packages", "blueprints", ".ref", ".github"}
    candidates = []
    for p in config_dir.glob("*.yaml"):
        if p.name.startswith("."):
            continue
        rel = p.relative_to(config_dir)
        parts = rel.parts
        if parts and parts[0] in excluded:
            continue
        candidates.append((p.name, str(p.resolve())))
    return sorted(candidates, key=lambda x: x[0].lower())


def check_esphome_config(yaml_path: str) -> tuple[bool, str]:
    """Run esphome config. Returns (ok, output)."""
    try:
        r = subprocess.run(
            ["esphome", "config", yaml_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode == 0:
            return True, r.stdout or ""
        return False, r.stderr or r.stdout or "Unknown error"
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def run_compile(yaml_path: str) -> tuple[bool, str]:
    """Run esphome compile. Returns (ok, combined_output)."""
    try:
        proc = subprocess.Popen(
            ["esphome", "compile", yaml_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output = []
        if proc.stdout:
            for line in proc.stdout:
                output.append(line.rstrip())
        proc.wait()
        return proc.returncode == 0, "\n".join(output)
    except FileNotFoundError:
        return False, "esphome not found. Install ESPHome: pip install esphome"


def run_upload(port: str, yaml_path: str, max_retries: int = 3) -> tuple[bool, str, str]:
    """Run esphome upload. Returns (success, port, output)."""
    import time
    out = "Unknown error"
    for attempt in range(max_retries):
        try:
            r = subprocess.run(
                ["esphome", "upload", "--device", port, yaml_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if r.returncode == 0:
                return True, port, r.stdout or "OK"
            out = r.stderr or r.stdout or "Unknown error"
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            out = str(e)
        if attempt < max_retries - 1:
            time.sleep(5)
    return False, port, out


@dataclass
class DeviceState:
    """Tracks devices and debounced disconnect counts."""

    previous: set[str] = field(default_factory=set)
    disconnect_counts: dict[str, int] = field(default_factory=dict)
    missing_polls: dict[str, int] = field(default_factory=dict)

    def update(self, new_devices: set[str]) -> None:
        for d in list(self.missing_polls.keys()):
            if d in new_devices:
                del self.missing_polls[d]
        for prev in self.previous:
            if prev not in new_devices:
                self.missing_polls[prev] = self.missing_polls.get(prev, 0) + 1
                if self.missing_polls[prev] >= DEBOUNCE_POLLS:
                    base = re.sub(r"\W", "_", os.path.basename(prev))
                    self.disconnect_counts[base] = self.disconnect_counts.get(base, 0) + 1
                    del self.missing_polls[prev]
        self.previous = new_devices

    def disconnect_count(self, device_path: str) -> int:
        base = re.sub(r"\W", "_", os.path.basename(device_path))
        return self.disconnect_counts.get(base, 0)


def _sort_key(device_path: str) -> int:
    m = re.search(r"\d+", os.path.basename(device_path))
    return int(m.group()) if m else 0


class DevicesUpdated(Message):
    """Message posted when device list changes."""

    def __init__(self, boards: list[tuple[str, str]], device_state: DeviceState) -> None:
        self.boards = boards
        self.device_state = device_state
        super().__init__()


class CompileResult(Message):
    """Message with compile output."""

    def __init__(self, line: str) -> None:
        self.line = line
        super().__init__()


class UploadStatus(Message):
    """Message for upload progress."""

    def __init__(self, port: str, status: str, output: str = "") -> None:
        self.port = port
        self.status = status
        self.output = output
        super().__init__()


class ZLoaderApp(App[None]):
    """Main zloader TUI application."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #top-bar {
        height: 3;
        padding: 0 1;
        dock: top;
    }
    #top-bar Horizontal {
        height: auto;
        align: center middle;
    }
    #yaml-select {
        width: 30;
        margin-right: 2;
    }
    #body {
        height: 1fr;
        padding: 1;
    }
    #left-panel {
        width: 35;
        min-width: 30;
        padding: 1;
        border: solid $primary;
    }
    #main-area {
        width: 1fr;
        padding: 1;
        border: solid $primary;
        min-height: 10;
    }
    RichLog {
        scrollbar-size: 1 2;
        padding: 1;
    }
    ListView {
        height: 1fr;
    }
    .device-item {
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, config_dir: Path) -> None:
        super().__init__()
        self.config_dir = config_dir
        self.device_state = DeviceState()
        self._boards: list[tuple[str, str]] = []
        self._yamls: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        self._yamls = discover_yamls(self.config_dir)
        yaml_options = [(name, path) for name, path in self._yamls] if self._yamls else [("(no yaml)", "")]

        with Container(id="top-bar"):
            yield Select(
                yaml_options,
                value=yaml_options[0][1] if yaml_options and yaml_options[0][1] else "",
                id="yaml-select",
                allow_blank=False,
            )
            yield Button("Compile", id="compile-btn", variant="primary")
            yield Button("Upload", id="upload-btn", variant="default")

        with Horizontal(id="body"):
            with Vertical(id="left-panel"):
                yield Static("Devices", classes="panel-title")
                yield ListView(id="device-list")

            with Vertical(id="main-area"):
                yield Static("Output", classes="panel-title")
                yield RichLog(id="output-log", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._refresh_devices())
        self.set_interval(POLL_INTERVAL, self._poll_devices)

    def _poll_devices(self) -> None:
        cu_devices = get_cu_usbmodem_devices()
        self.device_state.update(cu_devices)
        boards = get_connected_boards()
        if boards != self._boards:
            self._boards = boards
            self.post_message(DevicesUpdated(boards, self.device_state))

    async def _refresh_devices(self) -> None:
        cu_devices = get_cu_usbmodem_devices()
        self.device_state.update(cu_devices)
        self._boards = get_connected_boards()
        await self._update_device_list()

    async def _update_device_list(self) -> None:
        lst = self.query_one("#device-list", ListView)
        await lst.clear()
        sorted_boards = sorted(self._boards, key=lambda b: _sort_key(b[0]))
        for device_path, desc in sorted_boards:
            dc = self.device_state.disconnect_count(device_path)
            base = os.path.basename(device_path)
            label_text = f"{base}\n{desc}" + (f"  [dim]({dc} disconnects)[/]" if dc else "")
            await lst.append(ListItem(Label(label_text, classes="device-item")))
        if not sorted_boards:
            await lst.append(ListItem(Label("(no devices)", classes="device-item")))

    def on_devices_updated(self, m: DevicesUpdated) -> None:
        self._boards = m.boards
        self.device_state = m.device_state
        self.run_worker(self._update_device_list())

    def _get_selected_yaml(self) -> str | None:
        sel = self.query_one("#yaml-select", Select)
        val = sel.value
        if val and val != "(no yaml)":
            return str(val)
        return None

    def _log(self, text: str) -> None:
        log = self.query_one("#output-log", RichLog)
        log.write(text)

    def _clear_log(self) -> None:
        self.query_one("#output-log", RichLog).clear()

    def _disable_buttons(self, disabled: bool) -> None:
        self.query_one("#compile-btn", Button).disabled = disabled
        self.query_one("#upload-btn", Button).disabled = disabled

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "compile-btn":
            self.action_compile()
        elif event.button.id == "upload-btn":
            self.action_upload()

    def action_compile(self) -> None:
        yaml_path = self._get_selected_yaml()
        if not yaml_path:
            self._log("[red]Select a YAML file.[/]")
            return
        if not os.path.exists(yaml_path):
            self._log(f"[red]File not found: {yaml_path}[/]")
            return
        self._clear_log()
        self._disable_buttons(True)
        self.run_worker(
            self._compile_worker,
            yaml_path,
            thread=True,
        )

    def _compile_worker(self, yaml_path: str) -> None:
        def write_line(line: str) -> None:
            self.call_from_thread(self._log, line)

        self.call_from_thread(self._log, f"[dim]Compiling {yaml_path}...[/]\n")
        ok, output = run_compile(yaml_path)
        for line in output.splitlines():
            self.call_from_thread(self._log, line)
        self.call_from_thread(
            self._log,
            f"\n[{'green' if ok else 'red'}]{'Compile OK' if ok else 'Compile failed'}[/]",
        )
        self.call_from_thread(self._disable_buttons, False)

    def action_upload(self) -> None:
        yaml_path = self._get_selected_yaml()
        if not yaml_path:
            self._log("[red]Select a YAML file.[/]")
            return
        if not os.path.exists(yaml_path):
            self._log(f"[red]File not found: {yaml_path}[/]")
            return
        boards = get_connected_boards()
        if not boards:
            self._log("[red]No devices found. Connect ESP32 boards.[/]")
            return
        self._clear_log()
        self._disable_buttons(True)
        self.run_worker(
            self._upload_worker,
            yaml_path,
            list(boards),
            thread=True,
        )

    def _upload_worker(self, yaml_path: str, boards: list[tuple[str, str]]) -> None:
        def log(text: str) -> None:
            self.call_from_thread(self._log, text)

        def done() -> None:
            self.call_from_thread(self._disable_buttons, False)

        log(f"[dim]Uploading to {len(boards)} device(s)...[/]\n")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(boards)) as ex:
            futures = {
                ex.submit(run_upload, device, yaml_path): device
                for device, _ in boards
            }
            for future in concurrent.futures.as_completed(futures):
                device = futures[future]
                try:
                    success, port, output = future.result()
                    if success:
                        log(f"[green]{port}: OK[/]\n")
                    else:
                        log(f"[red]{port}: Failed[/]\n")
                        if output.strip():
                            for line in output.strip().splitlines()[:5]:
                                log(f"  [dim]{line}[/]\n")
                except Exception as e:
                    log(f"[red]{device}: {e}[/]\n")
        log("\n[dim]Uploads complete.[/]")
        done()


def main() -> None:
    parser = argparse.ArgumentParser(description="zloader - ESPHome uploader/compiler TUI")
    parser.add_argument(
        "--path",
        "-p",
        type=Path,
        default=None,
        help="Config directory (default: current directory)",
    )
    args = parser.parse_args()
    config_dir = args.path or Path.cwd()
    if not config_dir.is_dir():
        print(f"Not a directory: {config_dir}", file=sys.stderr)
        sys.exit(1)
    app = ZLoaderApp(config_dir)
    app.run()


if __name__ == "__main__":
    main()
