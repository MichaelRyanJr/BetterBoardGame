import argparse
import socket
import subprocess
import sys
import time

from board.led_driver import LEDDriver, empty_led_matrix
from board.token_scanner import TokenScanner
from shared.constants import Difficulty, LED_ON
from shared.game_state import Coordinate


MODE_SINGLE_PLAYER_SQUARE = Coordinate(3, 0)
MODE_MULTIPLAYER_SQUARE = Coordinate(4, 7)
SINGLE_PLAYER_DIFFICULTY_SQUARES = {
    Difficulty.EASY: Coordinate(7, 0),
    Difficulty.MEDIUM: Coordinate(7, 2),
    Difficulty.HARD: Coordinate(7, 4),
}

DEFAULT_SCAN_INTERVAL_SECONDS = 0.05
DEFAULT_MENU_BLINK_STEP_SECONDS = 0.35


class BootModeSelector:
    """
    Wait on the physical board for a startup selection.

    Startup flow:
    - place a piece on (3, 0) to enter single-player selection
    - then place a piece on:
        - (7, 0) for easy
        - (7, 2) for medium
        - (7, 4) for hard
    - place a piece on (4, 7) to enter multiplayer

    The menu remains the parent process. It launches the selected game as a
    child process, waits for that process to exit, then returns to the menu.
    """

    def __init__(
        self,
        scanner_mode="gpio",
        led_mode="hardware",
        scan_interval_seconds=DEFAULT_SCAN_INTERVAL_SECONDS,
        menu_blink_step_seconds=DEFAULT_MENU_BLINK_STEP_SECONDS,
        stable_reads_required=2,
        board_id=None,
        server_host=None,
        server_port=None,
        multiplayer_debug=False,
    ):
        self.scanner_mode = scanner_mode
        self.led_mode = led_mode
        self.stable_reads_required = stable_reads_required
        self.scan_interval_seconds = float(scan_interval_seconds)
        self.menu_blink_step_seconds = float(menu_blink_step_seconds)
        self.board_id = board_id
        self.server_host = server_host
        self.server_port = server_port
        self.multiplayer_debug = bool(multiplayer_debug)

        self.scanner = None
        self.led_driver = None

        self.stage = "mode_select"
        self.blink_started_at = time.monotonic()

        self.open_devices()
        self.reset_to_menu()

    def open_devices(self):
        self.scanner = TokenScanner(
            mode=self.scanner_mode,
            stable_reads_required=self.stable_reads_required,
        )
        self.led_driver = LEDDriver(mode=self.led_mode)

    def close_devices(self):
        if self.led_driver is not None:
            try:
                self.led_driver.clear()
            except Exception:
                pass

            try:
                self.led_driver.shutdown()
            except Exception:
                pass

            self.led_driver = None

        if self.scanner is not None:
            try:
                self.scanner.shutdown()
            except Exception:
                pass

            self.scanner = None

    def reset_blink_phase(self):
        self.blink_started_at = time.monotonic()

    def reset_to_menu(self):
        self.stage = "mode_select"
        self.reset_blink_phase()
        self.refresh_menu_leds()

    def square_is_occupied(self, scan_matrix, square):
        return bool(scan_matrix[square.row][square.col])

    def get_current_blink_is_on(self):
        if self.menu_blink_step_seconds <= 0:
            return True

        elapsed_seconds = time.monotonic() - self.blink_started_at
        phase_index = int(elapsed_seconds / self.menu_blink_step_seconds)
        return (phase_index % 2) == 0

    def build_blink_matrix(self, squares, blink_is_on):
        led_matrix = empty_led_matrix()

        if not blink_is_on:
            return led_matrix

        for square in squares:
            led_matrix[square.row][square.col] = LED_ON

        return led_matrix

    def refresh_menu_leds(self):
        if self.led_driver is None:
            return

        blink_is_on = self.get_current_blink_is_on()

        if self.stage == "mode_select":
            squares = [MODE_SINGLE_PLAYER_SQUARE, MODE_MULTIPLAYER_SQUARE]
        else:
            squares = [MODE_SINGLE_PLAYER_SQUARE]

            for difficulty in [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]:
                squares.append(SINGLE_PLAYER_DIFFICULTY_SQUARES[difficulty])

        led_matrix = self.build_blink_matrix(squares, blink_is_on)
        self.led_driver.set_led_matrix(led_matrix)

    def set_stage(self, stage):
        self.stage = stage
        self.reset_blink_phase()
        self.refresh_menu_leds()

    def build_single_player_command(self, difficulty):
        return [
            sys.executable,
            "-m",
            "board.run_single_player",
            "--difficulty",
            difficulty.value,
            "--scanner-mode",
            self.scanner_mode,
            "--led-mode",
            self.led_mode,
        ]

    def build_multiplayer_command(self):
        command = [
            sys.executable,
            "-m",
            "board.main",
        ]

        if self.board_id is not None:
            command.extend(["--board-id", self.board_id])

        if self.server_host is not None:
            command.extend(["--server-host", self.server_host])

        if self.server_port is not None:
            command.extend(["--server-port", str(self.server_port)])

        if self.multiplayer_debug:
            command.append("--debug")

        return command

    def launch_child_process(self, command, label):
        print("Launching", label + ":", " ".join(command))

        self.close_devices()

        try:
            completed = subprocess.run(command)
            print(label, "exited with return code", completed.returncode)
        finally:
            self.open_devices()
            self.reset_to_menu()

    def get_selected_single_player_difficulty(self, scan_matrix):
        selected_difficulty = None
        selected_count = 0

        for difficulty in [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]:
            square = SINGLE_PLAYER_DIFFICULTY_SQUARES[difficulty]

            if self.square_is_occupied(scan_matrix, square):
                selected_difficulty = difficulty
                selected_count += 1

        if selected_count == 1:
            return selected_difficulty

        return None

    def process_stable_scan(self, scan_matrix):
        if self.stage == "mode_select":
            single_player_selected = self.square_is_occupied(
                scan_matrix,
                MODE_SINGLE_PLAYER_SQUARE,
            )
            multiplayer_selected = self.square_is_occupied(
                scan_matrix,
                MODE_MULTIPLAYER_SQUARE,
            )

            if single_player_selected and not multiplayer_selected:
                print("Single-player mode selected. Waiting for difficulty.")
                self.set_stage("single_player_difficulty_select")
                return

            if multiplayer_selected and not single_player_selected:
                command = self.build_multiplayer_command()
                self.launch_child_process(command, "multiplayer")
                return

            return

        single_player_still_selected = self.square_is_occupied(
            scan_matrix,
            MODE_SINGLE_PLAYER_SQUARE,
        )

        if not single_player_still_selected:
            print("Single-player selection cleared. Returning to mode select.")
            self.set_stage("mode_select")
            return

        selected_difficulty = self.get_selected_single_player_difficulty(scan_matrix)

        if selected_difficulty is not None:
            command = self.build_single_player_command(selected_difficulty)
            self.launch_child_process(command, "single-player " + selected_difficulty.value)

    def run(self):
        print("Boot mode selector started.")
        print("Place a piece on (3, 0) for single player.")
        print("Place a piece on (4, 7) for multiplayer.")
        print("For single player, then place a piece on:")
        print("  (7, 0) easy")
        print("  (7, 2) medium")
        print("  (7, 4) hard")
        print("Press Ctrl+C to stop.")

        try:
            while True:
                self.refresh_menu_leds()
                stable_scan = self.scanner.read_stable_scan_matrix()

                if stable_scan is not None:
                    self.process_stable_scan(stable_scan)

                time.sleep(self.scan_interval_seconds)

        except KeyboardInterrupt:
            print("\nStopping boot mode selector.")
        finally:
            self.close_devices()


def parse_mode(value, allowed_values, argument_name):
    text = value.strip().lower()

    if text in allowed_values:
        return text

    allowed_text = ", ".join(allowed_values)
    raise argparse.ArgumentTypeError(
        argument_name + " must be one of: " + allowed_text
    )


def default_board_id():
    return socket.gethostname().lower()


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Select Better Board Game startup mode using physical board squares."
    )

    parser.add_argument(
        "--scanner-mode",
        type=lambda value: parse_mode(value, ["gpio", "mock"], "scanner-mode"),
        default="gpio",
        help="Scanner mode: gpio or mock.",
    )

    parser.add_argument(
        "--led-mode",
        type=lambda value: parse_mode(value, ["hardware", "mock"], "led-mode"),
        default="hardware",
        help="LED mode: hardware or mock.",
    )

    parser.add_argument(
        "--scan-interval",
        type=float,
        default=DEFAULT_SCAN_INTERVAL_SECONDS,
        help="Delay in seconds between selector loop iterations.",
    )

    parser.add_argument(
        "--menu-blink-step-seconds",
        type=float,
        default=DEFAULT_MENU_BLINK_STEP_SECONDS,
        help="On/off blink step for menu guidance LEDs.",
    )

    parser.add_argument(
        "--stable-reads-required",
        type=int,
        default=2,
        help="Stable reads required before accepting a menu selection.",
    )

    parser.add_argument(
        "--board-id",
        default=default_board_id(),
        help="Board ID to pass through to multiplayer mode.",
    )

    parser.add_argument(
        "--server-host",
        default=None,
        help="Optional server host override for multiplayer mode.",
    )

    parser.add_argument(
        "--server-port",
        type=int,
        default=None,
        help="Optional server port override for multiplayer mode.",
    )

    parser.add_argument(
        "--multiplayer-debug",
        action="store_true",
        help="Pass --debug through to board.main when launching multiplayer.",
    )

    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    selector = BootModeSelector(
        scanner_mode=args.scanner_mode,
        led_mode=args.led_mode,
        scan_interval_seconds=args.scan_interval,
        menu_blink_step_seconds=args.menu_blink_step_seconds,
        stable_reads_required=args.stable_reads_required,
        board_id=args.board_id,
        server_host=args.server_host,
        server_port=args.server_port,
        multiplayer_debug=args.multiplayer_debug,
    )
    selector.run()


if __name__ == "__main__":
    main()
