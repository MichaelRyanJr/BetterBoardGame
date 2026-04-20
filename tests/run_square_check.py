import argparse
import sys
import time
from pathlib import Path

# Make the repo root importable even when this file is run directly from /tests.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from board.led_driver import LEDDriver
from board.token_scanner import TokenScanner


def parse_mode(value, allowed_values, argument_name):
    text = value.strip().lower()

    if text in allowed_values:
        return text

    allowed_text = ", ".join(allowed_values)
    raise argparse.ArgumentTypeError(
        argument_name + " must be one of: " + allowed_text
    )


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Manual square-check test: detect stable scans and light matching LEDs."
    )

    parser.add_argument(
        "--scanner-mode",
        type=lambda value: parse_mode(value, ["gpio", "mock"], "scanner-mode"),
        default="gpio",
        help="Scanner mode: gpio or mock."
    )

    parser.add_argument(
        "--led-mode",
        type=lambda value: parse_mode(value, ["hardware", "mock"], "led-mode"),
        default="hardware",
        help="LED mode: hardware or mock."
    )

    parser.add_argument(
        "--stable-reads-required",
        type=int,
        default=2,
        help="How many matching scans are required before a scan is treated as stable."
    )

    parser.add_argument(
        "--loop-delay",
        type=float,
        default=0.05,
        help="Delay in seconds between scan attempts."
    )

    return parser


def build_occupied_square_list(scan_matrix):
    occupied_squares = []

    for row in range(8):
        for col in range(8):
            if scan_matrix[row][col]:
                occupied_squares.append((row, col))

    return occupied_squares


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        scanner = TokenScanner(
            mode=args.scanner_mode,
            stable_reads_required=args.stable_reads_required
        )

        led_driver = LEDDriver(mode=args.led_mode)

    except ImportError as error:
        print("Failed to start square check.")
        print(error)
        print()
        print("If you are running on the real board, make sure this Python environment")
        print("has the required Raspberry Pi hardware packages installed.")
        print("You can also test the script structure with:")
        print("python3 tests/run_square_check.py --scanner-mode mock --led-mode mock")
        return

    last_displayed_scan = None

    print("Square check started.")
    print("Scanner mode:", args.scanner_mode)
    print("LED mode:", args.led_mode)
    print("Place a piece on a playable square and the matching LED should light.")
    print("Remove the piece and the LED should turn off.")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            stable_scan = scanner.read_stable_scan_matrix()

            if stable_scan is not None:
                if stable_scan != last_displayed_scan:
                    led_driver.set_led_matrix(stable_scan)
                    last_displayed_scan = stable_scan

                    occupied_squares = build_occupied_square_list(stable_scan)
                    print("Occupied squares:", occupied_squares)

            time.sleep(args.loop_delay)

    except KeyboardInterrupt:
        print("\nStopping square check test.")

    finally:
        if "led_driver" in locals():
            led_driver.clear()
            led_driver.shutdown()

        if "scanner" in locals():
            scanner.shutdown()


if __name__ == "__main__":
    main()
