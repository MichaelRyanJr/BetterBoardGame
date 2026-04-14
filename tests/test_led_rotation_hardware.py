import os
import sys
import argparse
from time import sleep

CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_FILE_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import BOARD_SIZE, is_dark_square
from board.led_driver import LEDDriver


DEFAULT_SLOT_SHIFT = -1


def get_playable_cols_for_row(row):
    """
    Return the playable columns in left-to-right order for one logical row.
    For a normal checkers board, each row has 4 playable squares.
    """
    playable_cols = []

    for col in range(BOARD_SIZE):
        if is_dark_square(row, col):
            playable_cols.append(col)

    return playable_cols


def remap_playable_col_in_row(row, logical_col, slot_shift):
    """
    Remap one playable square within its row.

    This is the test-only correction for the behavior where the second LED
    lights first, then the rest, and the first LED lights last.

    slot_shift = -1 means:
      logical slot 0 -> target slot 3
      logical slot 1 -> target slot 0
      logical slot 2 -> target slot 1
      logical slot 3 -> target slot 2

    That is the correction that should cancel the observed one-step wrap.
    """
    playable_cols = get_playable_cols_for_row(row)

    logical_index = playable_cols.index(logical_col)
    mapped_index = (logical_index + slot_shift) % len(playable_cols)

    return playable_cols[mapped_index]


def build_remapped_checkerboard_matrix(slot_shift):
    """
    Build a full 8x8 matrix using the per-row playable-slot remap.
    """
    matrix = []

    for row in range(BOARD_SIZE):
        current_row = []

        for _ in range(BOARD_SIZE):
            current_row.append(False)

        matrix.append(current_row)

    for row in range(BOARD_SIZE):
        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(row, logical_col):
                continue

            mapped_col = remap_playable_col_in_row(
                row,
                logical_col,
                slot_shift
            )

            matrix[row][mapped_col] = True

    return matrix


def run_single_led_scan(driver, delay_seconds, slot_shift):
    """
    Light one playable square at a time, row by row.

    This keeps the original working test structure and only changes the
    playable-square mapping within each row.
    """
    for row in range(BOARD_SIZE):
        print("Testing row", row)

        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(row, logical_col):
                continue

            mapped_col = remap_playable_col_in_row(
                row,
                logical_col,
                slot_shift
            )

            print(
                "  Lighting logical square row=", row,
                "logical_col=", logical_col,
                "mapped_col=", mapped_col
            )

            driver.clear()
            driver.set_square(row, mapped_col, True)
            sleep(delay_seconds)

    driver.clear()


def run_row_fill_scan(driver, delay_seconds, slot_shift):
    """
    Fill one row's playable squares from left to right using the remapped order.
    """
    for row in range(BOARD_SIZE):
        print("Filling playable squares in row", row)

        driver.clear()

        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(row, logical_col):
                continue

            mapped_col = remap_playable_col_in_row(
                row,
                logical_col,
                slot_shift
            )

            print(
                "  Adding logical square row=", row,
                "logical_col=", logical_col,
                "mapped_col=", mapped_col
            )

            driver.set_square(row, mapped_col, True)
            sleep(delay_seconds)

        sleep(delay_seconds)

    driver.clear()


def run_checkerboard_hold_test(driver, delay_seconds, slot_shift):
    """
    Turn on every playable square at once using the remapped row ordering.
    """
    print("Turning on all playable squares")

    matrix = build_remapped_checkerboard_matrix(slot_shift)
    driver.set_led_matrix(matrix)
    sleep(delay_seconds)

    print("Turning all LEDs off")
    driver.clear()
    sleep(delay_seconds)


def build_argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between LED changes"
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=3,
        help="MAX7219 brightness from 0 to 15"
    )
    parser.add_argument(
        "--slot-shift",
        type=int,
        default=DEFAULT_SLOT_SHIFT,
        help="Playable-slot shift within each row. Use -1 for the current best guess."
    )
    parser.add_argument(
        "--mode",
        choices=["single", "row_fill", "checkerboard", "full"],
        default="full",
        help="Which test pattern to run"
    )
    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    driver = LEDDriver(
        mode="hardware",
        brightness=args.brightness
    )

    try:
        driver.clear()

        if args.mode == "single":
            run_single_led_scan(driver, args.delay, args.slot_shift)
        elif args.mode == "row_fill":
            run_row_fill_scan(driver, args.delay, args.slot_shift)
        elif args.mode == "checkerboard":
            run_checkerboard_hold_test(driver, args.delay, args.slot_shift)
        elif args.mode == "full":
            run_single_led_scan(driver, args.delay, args.slot_shift)
            run_row_fill_scan(driver, args.delay, args.slot_shift)
            run_checkerboard_hold_test(driver, args.delay, args.slot_shift)

        print("LED hardware test complete.")

    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
