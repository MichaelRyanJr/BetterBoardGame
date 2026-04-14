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
    Return the playable columns in left-to-right order for one row.
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
    Apply only the non-rotated per-row playable-slot correction.

    Current understanding:
    - even rows need a playable-slot shift of -1
    - odd rows need no shift

    This function does NOT rotate the board.
    It only fixes the order of playable LEDs inside each row.
    """
    if not is_dark_square(row, logical_col):
        raise ValueError(
            "logical_col must be a playable dark-square column for this row."
        )

    playable_cols = get_playable_cols_for_row(row)

    logical_index = None

    for index in range(len(playable_cols)):
        if playable_cols[index] == logical_col:
            logical_index = index
            break

    if logical_index is None:
        raise ValueError(
            "Could not find logical_col in the row's playable columns."
        )

    if (row % 2) == 0:
        slot_shift = even_row_slot_shift
    else:
        slot_shift = odd_row_slot_shift

    mapped_index = (logical_index + slot_shift) % len(playable_cols)
    mapped_col = playable_cols[mapped_index]

    return mapped_col


def map_logical_to_physical(
    logical_row,
    logical_col,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Map a logical square to the physical square for the baseline test.

    For this version:
    - row stays the same
    - only the playable-column ordering inside the row is corrected
    """
    if not is_dark_square(logical_row, logical_col):
        raise ValueError("Only playable dark squares can be mapped.")

    physical_row = logical_row
    physical_col = remap_playable_col_in_row(
        logical_row,
        logical_col,
        even_row_slot_shift,
        odd_row_slot_shift
    )

    return physical_row, physical_col


def build_row_corrected_checkerboard_matrix(
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Build a full 8x8 matrix using only the row-order correction.
    """
    matrix = []

    for _ in range(BOARD_SIZE):
        row = []

        for _ in range(BOARD_SIZE):
            row.append(False)

        matrix.append(row)

    for logical_row in range(BOARD_SIZE):
        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(logical_row, logical_col):
                continue

            physical_row, physical_col = map_logical_to_physical(
                logical_row,
                logical_col,
                even_row_slot_shift,
                odd_row_slot_shift
            )

            matrix[physical_row][physical_col] = True

    return matrix


def run_single_led_scan(
    driver,
    delay_seconds,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Light one logical playable square at a time.

    This is the best first test for checking whether the playable-square
    order inside each row is correct.
    """
    for logical_row in range(BOARD_SIZE):
        print("Testing logical row", logical_row)

        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(logical_row, logical_col):
                continue

            physical_row, physical_col = map_logical_to_physical(
                logical_row,
                logical_col,
                even_row_slot_shift,
                odd_row_slot_shift
            )

            print(
                "  Lighting logical square row=", logical_row,
                "logical_col=", logical_col,
                "-> physical_row=", physical_row,
                "physical_col=", physical_col
            )

            driver.clear()
            driver.set_square(physical_row, physical_col, True)
            sleep(delay_seconds)

    driver.clear()


def run_row_fill_scan(
    driver,
    delay_seconds,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Fill each logical row from left to right using only row-order correction.
    """
    for logical_row in range(BOARD_SIZE):
        print("Filling logical playable squares in row", logical_row)

        driver.clear()

        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(logical_row, logical_col):
                continue

            physical_row, physical_col = map_logical_to_physical(
                logical_row,
                logical_col,
                even_row_slot_shift,
                odd_row_slot_shift
            )

            print(
                "  Adding logical square row=", logical_row,
                "logical_col=", logical_col,
                "-> physical_row=", physical_row,
                "physical_col=", physical_col
            )

            driver.set_square(physical_row, physical_col, True)
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
    Turn on every corrected playable square at once.
    """
    print("Turning on all row-corrected playable squares")

    matrix = build_row_corrected_checkerboard_matrix(
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

        print("Baseline row-order LED hardware test complete.")

    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
