import os
import sys
import argparse
from time import sleep

CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_FILE_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import spidev
except ImportError:
    spidev = None


BOARD_SIZE = 8

MAX7219_REG_DIGIT0 = 0x01
MAX7219_REG_DIGIT1 = 0x02
MAX7219_REG_DIGIT2 = 0x03
MAX7219_REG_DIGIT3 = 0x04
MAX7219_REG_DIGIT4 = 0x05
MAX7219_REG_DIGIT5 = 0x06
MAX7219_REG_DIGIT6 = 0x07
MAX7219_REG_DIGIT7 = 0x08
MAX7219_REG_DECODE_MODE = 0x09
MAX7219_REG_INTENSITY = 0x0A
MAX7219_REG_SCAN_LIMIT = 0x0B
MAX7219_REG_SHUTDOWN = 0x0C
MAX7219_REG_DISPLAY_TEST = 0x0F

DEFAULT_SPI_BUS = 0
DEFAULT_SPI_DEVICE = 0
DEFAULT_SPI_SPEED_HZ = 1000000
DEFAULT_BRIGHTNESS = 3

# This is the same correction that fixed row order in the non-rotated test:
# - even rows need a one-slot wrap backward
# - odd rows stay unchanged
DEFAULT_EVEN_ROW_SLOT_SHIFT = -1
DEFAULT_ODD_ROW_SLOT_SHIFT = 0


def is_dark_square(row, col):
    return (row + col) % 2 == 1


def is_light_square(row, col):
    return not is_dark_square(row, col)


def get_playable_cols_for_row(row, playable_color):
    playable_cols = []

    for col in range(BOARD_SIZE):
        if playable_color == "dark":
            if is_dark_square(row, col):
                playable_cols.append(col)
        elif playable_color == "light":
            if is_light_square(row, col):
                playable_cols.append(col)
        else:
            raise ValueError("Unsupported playable_color: " + str(playable_color))

    return playable_cols


def rotate_logical_to_physical_cw(logical_row, logical_col):
    """
    Apply pure 90 degree clockwise rotation.

    logical row 0,col 0 -> physical row 0,col 7
    logical row 7,col 0 -> physical row 0,col 0
    logical row 0,col 7 -> physical row 7,col 7
    logical row 7,col 7 -> physical row 7,col 0
    """
    physical_row = logical_col
    physical_col = BOARD_SIZE - 1 - logical_row
    return physical_row, physical_col


def remap_rotated_physical_col(
    physical_row,
    raw_physical_col,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    After CW rotation, logical playable dark squares land on physical light squares.

    We then apply the row-specific playable-slot correction that already worked
    in the non-rotated test:
    - even physical rows: shift by -1
    - odd physical rows: shift by 0
    """
    physical_playable_cols = get_playable_cols_for_row(physical_row, "light")
    raw_slot_index = physical_playable_cols.index(raw_physical_col)

    if (physical_row % 2) == 0:
        slot_shift = even_row_slot_shift
    else:
        slot_shift = odd_row_slot_shift

    mapped_slot_index = (raw_slot_index + slot_shift) % len(physical_playable_cols)
    return physical_playable_cols[mapped_slot_index]


def map_logical_to_physical(
    logical_row,
    logical_col,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Full current test mapping:
    1. CW rotation
    2. row-specific playable-slot correction
    """
    raw_physical_row, raw_physical_col = rotate_logical_to_physical_cw(
        logical_row,
        logical_col
    )

    mapped_physical_col = remap_rotated_physical_col(
        raw_physical_row,
        raw_physical_col,
        even_row_slot_shift,
        odd_row_slot_shift
    )

    return raw_physical_row, mapped_physical_col


def empty_matrix():
    matrix = []

    for _ in range(BOARD_SIZE):
        row = []
        for _ in range(BOARD_SIZE):
            row.append(0)
        matrix.append(row)

    return matrix


class RawMAX7219:
    def __init__(
        self,
        spi_bus=DEFAULT_SPI_BUS,
        spi_device=DEFAULT_SPI_DEVICE,
        spi_speed_hz=DEFAULT_SPI_SPEED_HZ,
        brightness=DEFAULT_BRIGHTNESS
    ):
        if spidev is None:
            raise ImportError(
                "This test requires the 'spidev' package in your virtual environment."
            )

        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = int(spi_speed_hz)
        self.spi.mode = 0

        self.brightness = int(brightness)

        if self.brightness < 0 or self.brightness > 15:
            raise ValueError("brightness must be between 0 and 15.")

        self.initialize()

    def write_register(self, register_address, register_value):
        self.spi.xfer2([int(register_address), int(register_value)])

    def initialize(self):
        self.write_register(MAX7219_REG_DISPLAY_TEST, 0)
        self.write_register(MAX7219_REG_DECODE_MODE, 0)
        self.write_register(MAX7219_REG_SCAN_LIMIT, 7)
        self.write_register(MAX7219_REG_INTENSITY, self.brightness)
        self.write_register(MAX7219_REG_SHUTDOWN, 1)
        self.clear()

    def clear(self):
        for register_address in range(MAX7219_REG_DIGIT0, MAX7219_REG_DIGIT7 + 1):
            self.write_register(register_address, 0)

    def physical_row_to_digit_register(self, row):
        """
        Physical row 0 is the top row.
        DIG7 controls the top row and DIG0 controls the bottom row.
        """
        digit_index = (BOARD_SIZE - 1) - row
        return MAX7219_REG_DIGIT0 + digit_index

    def build_row_byte(self, row_values):
        """
        Bit 0 -> SEG A  -> leftmost physical column
        Bit 7 -> SEG DP -> rightmost physical column
        """
        row_byte = 0

        for col in range(BOARD_SIZE):
            if row_values[col]:
                row_byte = row_byte | (1 << col)

        return row_byte

    def write_matrix(self, matrix):
        for row in range(BOARD_SIZE):
            register_address = self.physical_row_to_digit_register(row)
            row_byte = self.build_row_byte(matrix[row])
            self.write_register(register_address, row_byte)

    def shutdown(self):
        try:
            self.clear()
            self.write_register(MAX7219_REG_SHUTDOWN, 0)
        finally:
            self.spi.close()


def run_single_led_scan(
    driver,
    delay_seconds,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Light one logical playable square at a time.
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
                "-> physical row=", physical_row,
                "physical_col=", physical_col
            )

            matrix = empty_matrix()
            matrix[physical_row][physical_col] = 1
            driver.write_matrix(matrix)
            sleep(delay_seconds)

    driver.clear()


def run_row_fill_scan(
    driver,
    delay_seconds,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Fill each logical playable row from left to right.
    """
    for logical_row in range(BOARD_SIZE):
        print("Filling logical playable squares in row", logical_row)

        matrix = empty_matrix()

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
                "-> physical row=", physical_row,
                "physical_col=", physical_col
            )

            matrix[physical_row][physical_col] = 1
            driver.write_matrix(matrix)
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
    Turn on all logical playable squares at once.
    """
    print("Turning on all logical playable squares")

    matrix = empty_matrix()

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

            matrix[physical_row][physical_col] = 1

    driver.write_matrix(matrix)
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
        default=DEFAULT_BRIGHTNESS,
        help="MAX7219 brightness from 0 to 15"
    )
    parser.add_argument(
        "--even-row-slot-shift",
        type=int,
        default=DEFAULT_EVEN_ROW_SLOT_SHIFT,
        help="Playable-slot shift used on even physical rows"
    )
    parser.add_argument(
        "--odd-row-slot-shift",
        type=int,
        default=DEFAULT_ODD_ROW_SLOT_SHIFT,
        help="Playable-slot shift used on odd physical rows"
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

    driver = RawMAX7219(brightness=args.brightness)

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

        print("LED CW rotation hardware test complete.")

    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
