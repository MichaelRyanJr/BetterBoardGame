import os
import sys

CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_FILE_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import argparse
from time import sleep

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


def is_dark_square(row, col):
    return (row + col) % 2 == 1


def empty_matrix():
    matrix = []

    for _ in range(BOARD_SIZE):
        row = []
        for _ in range(BOARD_SIZE):
            row.append(0)
        matrix.append(row)

    return matrix


def clone_matrix(matrix):
    cloned = []

    for row in matrix:
        cloned_row = []

        for value in row:
            cloned_row.append(int(value))

        cloned.append(cloned_row)

    return cloned


def rotate_matrix_clockwise(matrix):
    rotated = []

    for row in range(BOARD_SIZE):
        new_row = []

        for col in range(BOARD_SIZE):
            new_row.append(matrix[BOARD_SIZE - 1 - col][row])

        rotated.append(new_row)

    return rotated


def rotate_matrix_counterclockwise(matrix):
    rotated = []

    for row in range(BOARD_SIZE):
        new_row = []

        for col in range(BOARD_SIZE):
            new_row.append(matrix[col][BOARD_SIZE - 1 - row])

        rotated.append(new_row)

    return rotated


def rotate_matrix_180(matrix):
    rotated = []

    for row in range(BOARD_SIZE):
        new_row = []

        for col in range(BOARD_SIZE):
            new_row.append(matrix[BOARD_SIZE - 1 - row][BOARD_SIZE - 1 - col])

        rotated.append(new_row)

    return rotated


def logical_to_physical_matrix(logical_matrix, rotation):
    if rotation == "none":
        return clone_matrix(logical_matrix)

    if rotation == "cw":
        return rotate_matrix_clockwise(logical_matrix)

    if rotation == "ccw":
        return rotate_matrix_counterclockwise(logical_matrix)

    if rotation == "180":
        return rotate_matrix_180(logical_matrix)

    raise ValueError("Unsupported rotation: " + str(rotation))


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

    def software_row_to_digit_register(self, row):
        # Physical matrix row 0 is the top row.
        # DIG7 controls the top row and DIG0 controls the bottom row.
        digit_index = (BOARD_SIZE - 1) - row
        return MAX7219_REG_DIGIT0 + digit_index

    def build_row_byte(self, row_values):
        # Bit 0 -> SEG A -> leftmost column
        # Bit 7 -> SEG DP -> rightmost column
        row_byte = 0

        for col in range(BOARD_SIZE):
            if row_values[col]:
                row_byte = row_byte | (1 << col)

        return row_byte

    def write_matrix(self, matrix):
        for row in range(BOARD_SIZE):
            register_address = self.software_row_to_digit_register(row)
            row_byte = self.build_row_byte(matrix[row])
            self.write_register(register_address, row_byte)

    def shutdown(self):
        try:
            self.clear()
            self.write_register(MAX7219_REG_SHUTDOWN, 0)
        finally:
            self.spi.close()


def run_single_led_scan(driver, delay_seconds, rotation):
    """
    Light one logical playable square at a time, then rotate it into
    physical board orientation before sending it to hardware.
    """
    for row in range(BOARD_SIZE):
        print("Testing logical row", row)

        for col in range(BOARD_SIZE):
            if not is_dark_square(row, col):
                continue

            print("  Lighting logical square row=", row, "col=", col)

            logical_matrix = empty_matrix()
            logical_matrix[row][col] = 1

            physical_matrix = logical_to_physical_matrix(logical_matrix, rotation)
            driver.write_matrix(physical_matrix)
            sleep(delay_seconds)

    driver.clear()


def run_row_fill_scan(driver, delay_seconds, rotation):
    """
    Fill the logical playable squares in each row from left to right,
    then rotate that pattern into physical board orientation.
    """
    for row in range(BOARD_SIZE):
        print("Filling logical playable squares in row", row)

        logical_matrix = empty_matrix()

        for col in range(BOARD_SIZE):
            if not is_dark_square(row, col):
                continue

            logical_matrix[row][col] = 1

            physical_matrix = logical_to_physical_matrix(logical_matrix, rotation)
            driver.write_matrix(physical_matrix)
            sleep(delay_seconds)

        sleep(delay_seconds)

    driver.clear()


def run_checkerboard_hold_test(driver, delay_seconds, rotation):
    """
    Turn on every logical playable square at once, then rotate it into
    physical board orientation.
    """
    print("Turning on all logical playable squares")

    logical_matrix = empty_matrix()

    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if is_dark_square(row, col):
                logical_matrix[row][col] = 1

    physical_matrix = logical_to_physical_matrix(logical_matrix, rotation)
    driver.write_matrix(physical_matrix)
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
        "--rotation",
        choices=["none", "cw", "ccw", "180"],
        default="cw",
        help="How the physical board is rotated relative to logical software orientation"
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
            run_single_led_scan(driver, args.delay, args.rotation)
        elif args.mode == "row_fill":
            run_row_fill_scan(driver, args.delay, args.rotation)
        elif args.mode == "checkerboard":
            run_checkerboard_hold_test(driver, args.delay, args.rotation)
        elif args.mode == "full":
            run_single_led_scan(driver, args.delay, args.rotation)
            run_row_fill_scan(driver, args.delay, args.rotation)
            run_checkerboard_hold_test(driver, args.delay, args.rotation)

        print("LED rotation hardware test complete.")

    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
