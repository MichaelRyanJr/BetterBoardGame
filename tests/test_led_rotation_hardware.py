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

# Confirmed board-level assumptions
DEFAULT_ROTATION = "cw"

# Canonical software checkers board still uses dark squares as playable
DEFAULT_LOGICAL_PLAYABLE_COLOR = "dark"

# After the 90 degree physical rotation, the physically populated LED parity flips
DEFAULT_PHYSICAL_PLAYABLE_COLOR = "light"

# Real row remap, not just test order:
# what used to be row 1 now behaves like row 0, and old row 0 wraps to the end
DEFAULT_PHYSICAL_ROW_REMAP = [1, 2, 3, 4, 5, 6, 7, 0]

# Slot remap for the affected physical rows:
# logical slot 0 -> physical slot 1
# logical slot 1 -> physical slot 2
# logical slot 2 -> physical slot 3
# logical slot 3 -> physical slot 0
DEFAULT_AFFECTED_ROW_SLOT_REMAP = [1, 2, 3, 0]

# Rows not affected keep normal slot order
DEFAULT_NORMAL_ROW_SLOT_REMAP = [0, 1, 2, 3]

# Based on your latest observation, the affected rows are the odd physical rows
DEFAULT_AFFECTED_ROW_PARITY = "odd"


def is_dark_square(row, col):
    return (row + col) % 2 == 1


def row_matches_parity(row, parity_name):
    if parity_name == "even":
        return (row % 2) == 0

    if parity_name == "odd":
        return (row % 2) == 1

    if parity_name == "none":
        return False

    raise ValueError("Unsupported parity name: " + str(parity_name))


def is_playable_square_for_color(row, col, playable_color):
    if playable_color == "dark":
        return is_dark_square(row, col)

    if playable_color == "light":
        return not is_dark_square(row, col)

    raise ValueError("Unsupported playable_color: " + str(playable_color))


def get_playable_cols_for_row(row, playable_color):
    playable_cols = []

    for col in range(BOARD_SIZE):
        if is_playable_square_for_color(row, col, playable_color):
            playable_cols.append(col)

    return playable_cols


def get_playable_index_in_row(row, col, playable_color):
    playable_cols = get_playable_cols_for_row(row, playable_color)

    for index, playable_col in enumerate(playable_cols):
        if playable_col == col:
            return index

    raise ValueError(
        "Column " + str(col) + " is not a playable column in row " + str(row) + "."
    )


def empty_matrix():
    matrix = []

    for _ in range(BOARD_SIZE):
        row = []
        for _ in range(BOARD_SIZE):
            row.append(0)
        matrix.append(row)

    return matrix


def rotate_logical_to_raw_physical(row, col, rotation):
    if rotation == "none":
        return row, col

    if rotation == "cw":
        return col, BOARD_SIZE - 1 - row

    if rotation == "ccw":
        return BOARD_SIZE - 1 - col, row

    if rotation == "180":
        return BOARD_SIZE - 1 - row, BOARD_SIZE - 1 - col

    raise ValueError("Unsupported rotation: " + str(rotation))


def choose_slot_remap_for_row(physical_row, affected_row_parity):
    if row_matches_parity(physical_row, affected_row_parity):
        return list(DEFAULT_AFFECTED_ROW_SLOT_REMAP)

    return list(DEFAULT_NORMAL_ROW_SLOT_REMAP)


def map_logical_to_physical(
    logical_row,
    logical_col,
    rotation,
    logical_playable_color,
    physical_playable_color,
    physical_row_remap,
    affected_row_parity
):
    """
    Convert one canonical logical square into the actual physical LED position
    on the currently wired board.

    Steps:
    1. Apply board rotation
    2. Preserve the playable-slot index in the raw rotated row
    3. Apply the physical row remap
    4. On affected rows, remap the 4 playable slots as [1,2,3,0]
    """
    raw_physical_row, raw_physical_col = rotate_logical_to_raw_physical(
        logical_row,
        logical_col,
        rotation
    )

    raw_slot_index = get_playable_index_in_row(
        raw_physical_row,
        raw_physical_col,
        physical_playable_color
    )

    physical_row = physical_row_remap[raw_physical_row]

    slot_remap = choose_slot_remap_for_row(
        physical_row,
        affected_row_parity
    )

    corrected_slot_index = slot_remap[raw_slot_index]

    playable_cols = get_playable_cols_for_row(
        physical_row,
        physical_playable_color
    )

    physical_col = playable_cols[corrected_slot_index]

    return physical_row, physical_col


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
    rotation,
    logical_playable_color,
    physical_playable_color,
    physical_row_remap,
    affected_row_parity
):
    """
    Light one logical playable square at a time.
    """
    for logical_row in range(BOARD_SIZE):
        print("Testing logical row", logical_row)

        for logical_col in range(BOARD_SIZE):
            if not is_playable_square_for_color(
                logical_row,
                logical_col,
                logical_playable_color
            ):
                continue

            physical_row, physical_col = map_logical_to_physical(
                logical_row,
                logical_col,
                rotation,
                logical_playable_color,
                physical_playable_color,
                physical_row_remap,
                affected_row_parity
            )

            print(
                "  Lighting logical square row=", logical_row,
                "col=", logical_col,
                "-> physical row=", physical_row,
                "col=", physical_col
            )

            matrix = empty_matrix()
            matrix[physical_row][physical_col] = 1

            driver.write_matrix(matrix)
            sleep(delay_seconds)

    driver.clear()


def run_row_fill_scan(
    driver,
    delay_seconds,
    rotation,
    logical_playable_color,
    physical_playable_color,
    physical_row_remap,
    affected_row_parity
):
    """
    Fill each logical playable row from left to right.
    """
    for logical_row in range(BOARD_SIZE):
        print("Filling logical playable squares in row", logical_row)

        matrix = empty_matrix()

        for logical_col in range(BOARD_SIZE):
            if not is_playable_square_for_color(
                logical_row,
                logical_col,
                logical_playable_color
            ):
                continue

            physical_row, physical_col = map_logical_to_physical(
                logical_row,
                logical_col,
                rotation,
                logical_playable_color,
                physical_playable_color,
                physical_row_remap,
                affected_row_parity
            )

            print(
                "  Adding logical square row=", logical_row,
                "col=", logical_col,
                "-> physical row=", physical_row,
                "col=", physical_col
            )

            matrix[physical_row][physical_col] = 1
            driver.write_matrix(matrix)
            sleep(delay_seconds)

        sleep(delay_seconds)

    driver.clear()


def run_checkerboard_hold_test(
    driver,
    delay_seconds,
    rotation,
    logical_playable_color,
    physical_playable_color,
    physical_row_remap,
    affected_row_parity
):
    """
    Turn on all logical playable squares at once.
    """
    print("Turning on all logical playable squares")

    matrix = empty_matrix()

    for logical_row in range(BOARD_SIZE):
        for logical_col in range(BOARD_SIZE):
            if not is_playable_square_for_color(
                logical_row,
                logical_col,
                logical_playable_color
            ):
                continue

            physical_row, physical_col = map_logical_to_physical(
                logical_row,
                logical_col,
                rotation,
                logical_playable_color,
                physical_playable_color,
                physical_row_remap,
                affected_row_parity
            )

            matrix[physical_row][physical_col] = 1

    driver.write_matrix(matrix)
    sleep(delay_seconds)

    print("Turning all LEDs off")
    driver.clear()
    sleep(delay_seconds)


def parse_row_remap(text):
    parts = text.split(",")

    if len(parts) != BOARD_SIZE:
        raise ValueError("row remap must contain exactly 8 comma-separated integers.")

    row_remap = []

    for part in parts:
        row_remap.append(int(part.strip()))

    if sorted(row_remap) != list(range(BOARD_SIZE)):
        raise ValueError("row remap must be a permutation of 0 through 7.")

    return row_remap


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
        "--rotation",
        choices=["none", "cw", "ccw", "180"],
        default=DEFAULT_ROTATION,
        help="How the physical board is rotated relative to logical software orientation"
    )
    parser.add_argument(
        "--logical-playable-color",
        choices=["dark", "light"],
        default=DEFAULT_LOGICAL_PLAYABLE_COLOR,
        help="Canonical software playable parity"
    )
    parser.add_argument(
        "--physical-playable-color",
        choices=["dark", "light"],
        default=DEFAULT_PHYSICAL_PLAYABLE_COLOR,
        help="Physically populated LED parity"
    )
    parser.add_argument(
        "--physical-row-remap",
        default="1,2,3,4,5,6,7,0",
        help="Comma-separated row remap after rotation"
    )
    parser.add_argument(
        "--affected-row-parity",
        choices=["even", "odd", "none"],
        default=DEFAULT_AFFECTED_ROW_PARITY,
        help="Which physical row parity gets the [1,2,3,0] slot remap"
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

    physical_row_remap = parse_row_remap(args.physical_row_remap)

    driver = RawMAX7219(brightness=args.brightness)

    try:
        driver.clear()

        if args.mode == "single":
            run_single_led_scan(
                driver,
                args.delay,
                args.rotation,
                args.logical_playable_color,
                args.physical_playable_color,
                physical_row_remap,
                args.affected_row_parity
            )
        elif args.mode == "row_fill":
            run_row_fill_scan(
                driver,
                args.delay,
                args.rotation,
                args.logical_playable_color,
                args.physical_playable_color,
                physical_row_remap,
                args.affected_row_parity
            )
        elif args.mode == "checkerboard":
            run_checkerboard_hold_test(
                driver,
                args.delay,
                args.rotation,
                args.logical_playable_color,
                args.physical_playable_color,
                physical_row_remap,
                args.affected_row_parity
            )
        elif args.mode == "full":
            run_single_led_scan(
                driver,
                args.delay,
                args.rotation,
                args.logical_playable_color,
                args.physical_playable_color,
                physical_row_remap,
                args.affected_row_parity
            )
            run_row_fill_scan(
                driver,
                args.delay,
                args.rotation,
                args.logical_playable_color,
                args.physical_playable_color,
                physical_row_remap,
                args.affected_row_parity
            )
            run_checkerboard_hold_test(
                driver,
                args.delay,
                args.rotation,
                args.logical_playable_color,
                args.physical_playable_color,
                physical_row_remap,
                args.affected_row_parity
            )

        print("LED rotation hardware test complete.")

    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
