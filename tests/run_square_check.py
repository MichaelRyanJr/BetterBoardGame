import sys
import time
from pathlib import Path

# Make the repo root importable even when this file is run directly from /tests.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from board.led_driver import LEDDriver
from board.token_scanner import TokenScanner


def build_occupied_square_list(scan_matrix):
    occupied_squares = []

    for row in range(8):
        for col in range(8):
            if scan_matrix[row][col]:
                occupied_squares.append((row, col))

    return occupied_squares


def main():
    scanner = TokenScanner(
        mode="gpio",
        stable_reads_required=2
    )

    led_driver = LEDDriver(mode="hardware")

    last_displayed_scan = None

    print("Square check started.")
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

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopping square check test.")

    finally:
        led_driver.clear()
        scanner.shutdown()
        led_driver.shutdown()


if __name__ == "__main__":
    main()
