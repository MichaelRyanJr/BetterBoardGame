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


DEFAULT_EVEN_ROW_SLOT_SHIFT = -1
DEFAULT_ODD_ROW_SLOT_SHIFT = 0


def get_playable_cols_for_row(row):
    """
    Return the playable columns in left-to-right order for one logical row.
    """
    playable_cols = []

    for col in range(BOARD_SIZE):
        if is_dark_square(row, col):
            playable_cols.append(col)

    return playable_cols


def remap_playable_col_in_row(
    row,
    logical_col,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Remap one playable square within its row.

    Current observed hardware behavior:
    - odd rows already behave correctly
    - even rows are one playable slot ahead

    So:
    - even rows use -1 playable-slot shift
    - odd rows use 0 playable-slot shift
    """
    playable_cols = get_playable_cols_for_row(row)
    logical_index = playable_cols.index(logical_col)

    if (row % 2) == 0:
        slot_shift = even_row_slot_shift
    else:
        slot_shift = odd_row_slot_shift

    mapped_index = (logical_index + slot_shift) % len(playable_cols)
    return playable_cols[mapped_index]


def build_remapped_checkerboard_matrix(
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Build a full 8x8 matrix using the per-row playable-slot remap.
    """
    matrix = []

    for _ in range(BOARD_SIZE):
        row = []
        for _ in range(BOARD_SIZE):
            row.append(False)
        matrix.append(row)

    for row in range(BOARD_SIZE):
        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(row, logical_col):
                continue

            mapped_col = remap_playable_col_in_row(
                row,
                logical_col,
                even_row_slot_shift,
                odd_row_slot_shift
            )

            matrix[row][mapped_col] = True

    return matrix


def run_single_led_scan(
    driver,
    delay_seconds,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Light one playable square at a time, row by row.
    """
    for row in range(BOARD_SIZE):
        print("Testing row", row)

        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(row, logical_col):
                continue

            mapped_col = remap_playable_col_in_row(
                row,
                logical_col,
                even_row_slot_shift,
                odd_row_slot_shift
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


def run_row_fill_scan(
    driver,
    delay_seconds,
    even_row_slot_shift,
    odd_row_slot_shift
):
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
                even_row_slot_shift,
                odd_row_slot_shift
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


def run_checkerboard_hold_test(
    driver,
    delay_seconds,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Turn on every playable square at once using the remapped row ordering.
    """
    print("Turning on all playable squares")

    matrix = build_remapped_checkerboard_matrix(
        even_row_slot_shift,
        odd_row_slot_shift
    )

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
        "--even-row-slot-shift",
        type=int,
        default=DEFAULT_EVEN_ROW_SLOT_SHIFT,
        help="Playable-slot shift used on even rows"
    )
    parser.add_argument(
        "--odd-row-slot-shift",
        type=int,
        default=DEFAULT_ODD_ROW_SLOT_SHIFT,
        help="Playable-slot shift used on odd rows"
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
            run_single_led_scan(
                driver,
                args.delay,
                args.even_row_slot_shift,
                args.odd_row_slot_shift
            )
        elif args.mode == "row_fill":
            run_row_fill_scan(
                driver,
                args.delay,
                args.even_row_slot_shift,
                args.odd_row_slot_shift
            )
        elif args.mode == "checkerboard":
            run_checkerboard_hold_test(
                driver,
                args.delay,
                args.even_row_slot_shift,
                args.odd_row_slot_shift
            )
        elif args.mode == "full":
            run_single_led_scan(
                driver,
                args.delay,
                args.even_row_slot_shift,
                args.odd_row_slot_shift
            )
            run_row_fill_scan(
                driver,
                args.delay,
                args.even_row_slot_shift,
                args.odd_row_slot_shift
            )
            run_checkerboard_hold_test(
                driver,
                args.delay,
                args.even_row_slot_shift,
                args.odd_row_slot_shift
            )

        print("LED hardware test complete.")

    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
