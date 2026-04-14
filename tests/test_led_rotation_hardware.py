""" 
DO NOT USE... this file was only to debug the wiring error we made and is no longer needed since
it doesn't actually test anything to do with the runtime files, use test_led_driver_hardware.py instead
"""

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
DEFAULT_COL_SHIFT_AFTER_CW = -1
DEFAULT_EVEN_COL_SLOT_SHIFT = 1
DEFAULT_ODD_COL_SLOT_SHIFT = 0


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
    Apply the already-confirmed non-rotated playable-slot correction.

    Current understanding:
    - even rows need a playable-slot shift of -1
    - odd rows need no shift
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


def map_logical_to_baseline_physical(
    logical_row,
    logical_col,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Apply only the known-good non-rotated mapping.

    This is the mapping that already gave the correct playable-slot order
    inside each row before rotation was introduced.
    """
    baseline_row = logical_row
    baseline_col = remap_playable_col_in_row(
        logical_row,
        logical_col,
        even_row_slot_shift,
        odd_row_slot_shift
    )

    return baseline_row, baseline_col


def rotate_coordinate_cw(row, col):
    """
    Apply a pure 90 degree clockwise rotation.

    (row, col) -> (col, 7 - row)
    """
    rotated_row = col
    rotated_col = BOARD_SIZE - 1 - row
    return rotated_row, rotated_col


def get_playable_rows_for_col(col):
    """
    Return the playable rows in top-to-bottom order for one column.
    """
    playable_rows = []

    for row in range(BOARD_SIZE):
        if is_dark_square(row, col):
            playable_rows.append(row)

    return playable_rows


def remap_playable_row_in_col(
    col,
    logical_row,
    even_col_slot_shift,
    odd_col_slot_shift
):
    """
    Apply the rotated per-column playable-slot correction.

    Current understanding:
    - even columns need a playable-slot shift of +1
    - odd columns need no shift
    """
    if not is_dark_square(logical_row, col):
        raise ValueError(
            "logical_row must be a playable dark-square row for this column."
        )

    playable_rows = get_playable_rows_for_col(col)

    logical_index = None

    for index in range(len(playable_rows)):
        if playable_rows[index] == logical_row:
            logical_index = index
            break

    if logical_index is None:
        raise ValueError(
            "Could not find logical_row in the column's playable rows."
        )

    if (col % 2) == 0:
        slot_shift = even_col_slot_shift
    else:
        slot_shift = odd_col_slot_shift

    mapped_index = (logical_index + slot_shift) % len(playable_rows)
    mapped_row = playable_rows[mapped_index]

    return mapped_row


def map_logical_to_physical(
    logical_row,
    logical_col,
    col_shift_after_cw,
    even_row_slot_shift,
    odd_row_slot_shift,
    even_col_slot_shift,
    odd_col_slot_shift
):
    """
    Final mapping for this test version:

    1. apply the known-good baseline row-order correction
    2. rotate 90 degrees clockwise
    3. shift columns so the rotated board starts in the correct place
    4. fix the remaining even-column wrap inside rotated columns
    """
    if not is_dark_square(logical_row, logical_col):
        raise ValueError("Only playable dark squares can be mapped.")

    baseline_row, baseline_col = map_logical_to_baseline_physical(
        logical_row,
        logical_col,
        even_row_slot_shift,
        odd_row_slot_shift
    )

    rotated_row, rotated_col = rotate_coordinate_cw(
        baseline_row,
        baseline_col
    )

    physical_col = (rotated_col + col_shift_after_cw) % BOARD_SIZE
    physical_row = rotated_row

    if not is_dark_square(physical_row, physical_col):
        raise ValueError(
            "Mapped square landed on a non-playable tile before column-row correction: "
            + "logical=(" + str(logical_row) + "," + str(logical_col) + ") "
            + "-> baseline=(" + str(baseline_row) + "," + str(baseline_col) + ") "
            + "-> rotated=(" + str(rotated_row) + "," + str(rotated_col) + ") "
            + "-> shifted=(" + str(physical_row) + "," + str(physical_col) + ")"
        )

    physical_row = remap_playable_row_in_col(
        physical_col,
        physical_row,
        even_col_slot_shift,
        odd_col_slot_shift
    )

    if not is_dark_square(physical_row, physical_col):
        raise ValueError(
            "Final mapped square landed on a non-playable tile: "
            + "logical=(" + str(logical_row) + "," + str(logical_col) + ") "
            + "-> physical=(" + str(physical_row) + "," + str(physical_col) + ")"
        )

    return physical_row, physical_col


def build_rotated_checkerboard_matrix(
    col_shift_after_cw,
    even_row_slot_shift,
    odd_row_slot_shift,
    even_col_slot_shift,
    odd_col_slot_shift
):
    """
    Build the full rotated/remapped checkerboard matrix.
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
                col_shift_after_cw,
                even_row_slot_shift,
                odd_row_slot_shift,
                even_col_slot_shift,
                odd_col_slot_shift
            )

            matrix[physical_row][physical_col] = True

    return matrix


def run_single_led_scan(
    driver,
    delay_seconds,
    col_shift_after_cw,
    even_row_slot_shift,
    odd_row_slot_shift,
    even_col_slot_shift,
    odd_col_slot_shift
):
    """
    Light one logical playable square at a time after CW rotation.
    """
    for logical_row in range(BOARD_SIZE):
        print("Testing logical row", logical_row)

        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(logical_row, logical_col):
                continue

            baseline_row, baseline_col = map_logical_to_baseline_physical(
                logical_row,
                logical_col,
                even_row_slot_shift,
                odd_row_slot_shift
            )

            physical_row, physical_col = map_logical_to_physical(
                logical_row,
                logical_col,
                col_shift_after_cw,
                even_row_slot_shift,
                odd_row_slot_shift,
                even_col_slot_shift,
                odd_col_slot_shift
            )

            print(
                "  Lighting logical square row=", logical_row,
                "logical_col=", logical_col,
                "-> baseline_row=", baseline_row,
                "baseline_col=", baseline_col,
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
    col_shift_after_cw,
    even_row_slot_shift,
    odd_row_slot_shift,
    even_col_slot_shift,
    odd_col_slot_shift
):
    """
    Fill each logical row from left to right after CW rotation.
    """
    for logical_row in range(BOARD_SIZE):
        print("Filling logical playable squares in row", logical_row)

        driver.clear()

        for logical_col in range(BOARD_SIZE):
            if not is_dark_square(logical_row, logical_col):
                continue

            baseline_row, baseline_col = map_logical_to_baseline_physical(
                logical_row,
                logical_col,
                even_row_slot_shift,
                odd_row_slot_shift
            )

            physical_row, physical_col = map_logical_to_physical(
                logical_row,
                logical_col,
                col_shift_after_cw,
                even_row_slot_shift,
                odd_row_slot_shift,
                even_col_slot_shift,
                odd_col_slot_shift
            )

            print(
                "  Adding logical square row=", logical_row,
                "logical_col=", logical_col,
                "-> baseline_row=", baseline_row,
                "baseline_col=", baseline_col,
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
    col_shift_after_cw,
    even_row_slot_shift,
    odd_row_slot_shift,
    even_col_slot_shift,
    odd_col_slot_shift
):
    """
    Turn on every rotated/remapped playable square at once.
    """
    print("Turning on all rotated playable squares")

    matrix = build_rotated_checkerboard_matrix(
        col_shift_after_cw,
        even_row_slot_shift,
        odd_row_slot_shift,
        even_col_slot_shift,
        odd_col_slot_shift
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
        "--col-shift-after-cw",
        type=int,
        default=DEFAULT_COL_SHIFT_AFTER_CW,
        help="Column shift applied after CW rotation to place columns correctly"
    )
    parser.add_argument(
        "--even-row-slot-shift",
        type=int,
        default=DEFAULT_EVEN_ROW_SLOT_SHIFT,
        help="Playable-slot shift used on even rows before rotation"
    )
    parser.add_argument(
        "--odd-row-slot-shift",
        type=int,
        default=DEFAULT_ODD_ROW_SLOT_SHIFT,
        help="Playable-slot shift used on odd rows before rotation"
    )
    parser.add_argument(
        "--even-col-slot-shift",
        type=int,
        default=DEFAULT_EVEN_COL_SLOT_SHIFT,
        help="Playable-slot shift used on even columns after rotation"
    )
    parser.add_argument(
        "--odd-col-slot-shift",
        type=int,
        default=DEFAULT_ODD_COL_SLOT_SHIFT,
        help="Playable-slot shift used on odd columns after rotation"
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
                args.col_shift_after_cw,
                args.even_row_slot_shift,
                args.odd_row_slot_shift,
                args.even_col_slot_shift,
                args.odd_col_slot_shift
            )
        elif args.mode == "row_fill":
            run_row_fill_scan(
                driver,
                args.delay,
                args.col_shift_after_cw,
                args.even_row_slot_shift,
                args.odd_row_slot_shift,
                args.even_col_slot_shift,
                args.odd_col_slot_shift
            )
        elif args.mode == "checkerboard":
            run_checkerboard_hold_test(
                driver,
                args.delay,
                args.col_shift_after_cw,
                args.even_row_slot_shift,
                args.odd_row_slot_shift,
                args.even_col_slot_shift,
                args.odd_col_slot_shift
            )
        elif args.mode == "full":
            run_single_led_scan(
                driver,
                args.delay,
                args.col_shift_after_cw,
                args.even_row_slot_shift,
                args.odd_row_slot_shift,
                args.even_col_slot_shift,
                args.odd_col_slot_shift
            )
            run_row_fill_scan(
                driver,
                args.delay,
                args.col_shift_after_cw,
                args.even_row_slot_shift,
                args.odd_row_slot_shift,
                args.even_col_slot_shift,
                args.odd_col_slot_shift
            )
            run_checkerboard_hold_test(
                driver,
                args.delay,
                args.col_shift_after_cw,
                args.even_row_slot_shift,
                args.odd_row_slot_shift,
                args.even_col_slot_shift,
                args.odd_col_slot_shift
            )

        print("CW rotation LED hardware test complete.")

    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
