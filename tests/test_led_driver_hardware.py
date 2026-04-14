import argparse
from time import sleep

from shared.constants import BOARD_SIZE, is_dark_square
from board.led_driver import LEDDriver


def run_single_led_scan(driver, delay_seconds):
    """
    Light one playable square at a time, row by row.
    """
    for row in range(BOARD_SIZE):
        print("Testing row", row)

        for col in range(BOARD_SIZE):
            if not is_dark_square(row, col):
                continue

            print("  Lighting square row=", row, "col=", col)

            driver.clear()
            driver.set_square(row, col, True)
            sleep(delay_seconds)

    driver.clear()


def run_row_fill_scan(driver, delay_seconds):
    """
    Fill each playable square in a row from left to right.
    """
    for row in range(BOARD_SIZE):
        print("Filling playable squares in row", row)

        driver.clear()

        for col in range(BOARD_SIZE):
            if not is_dark_square(row, col):
                continue

            driver.set_square(row, col, True)
            sleep(delay_seconds)

        sleep(delay_seconds)

    driver.clear()


def run_checkerboard_hold_test(driver, delay_seconds):
    """
    Turn on every playable dark square at once.
    """
    print("Turning on all playable squares")

    matrix = []

    for row in range(BOARD_SIZE):
        current_row = []

        for col in range(BOARD_SIZE):
            if is_dark_square(row, col):
                current_row.append(True)
            else:
                current_row.append(False)

        matrix.append(current_row)

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
            run_single_led_scan(driver, args.delay)
        elif args.mode == "row_fill":
            run_row_fill_scan(driver, args.delay)
        elif args.mode == "checkerboard":
            run_checkerboard_hold_test(driver, args.delay)
        elif args.mode == "full":
            run_single_led_scan(driver, args.delay)
            run_row_fill_scan(driver, args.delay)
            run_checkerboard_hold_test(driver, args.delay)

        print("LED hardware test complete.")

    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
