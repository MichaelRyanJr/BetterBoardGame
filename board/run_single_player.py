import argparse
import time

from board.led_driver import empty_led_matrix
from board.single_player_runtime import SinglePlayerRuntime
from shared.constants import Difficulty, LED_ON, Player
from shared.constants import is_dark_square


POST_GAME_SCAN_INTERVAL_SECONDS = 0.05
BOARD_CLEAR_REQUEST_BLINK_COUNT = 5
BOARD_CLEAR_REQUEST_BLINK_STEP_SECONDS = 0.2


def parse_difficulty(value):
    text = value.strip().lower()

    if text == "easy":
        return Difficulty.EASY

    if text == "medium":
        return Difficulty.MEDIUM

    if text == "hard":
        return Difficulty.HARD

    raise argparse.ArgumentTypeError(
        "difficulty must be 'easy', 'medium', or 'hard'."
    )


def parse_mode(value, allowed_values, argument_name):
    text = value.strip().lower()

    if text in allowed_values:
        return text

    allowed_text = ", ".join(allowed_values)
    raise argparse.ArgumentTypeError(
        argument_name + " must be one of: " + allowed_text
    )


def scan_is_empty(scan_matrix):
    for row in range(8):
        for col in range(8):
            if scan_matrix[row][col]:
                return False

    return True


def build_all_playable_leds_on_matrix():
    led_matrix = empty_led_matrix()

    for row in range(8):
        for col in range(8):
            if is_dark_square(row, col):
                led_matrix[row][col] = LED_ON

    return led_matrix


def blink_all_leds_for_board_clear_request(runtime):
    on_matrix = build_all_playable_leds_on_matrix()
    off_matrix = empty_led_matrix()

    for _ in range(BOARD_CLEAR_REQUEST_BLINK_COUNT):
        runtime.led_driver.set_led_matrix(on_matrix)
        time.sleep(BOARD_CLEAR_REQUEST_BLINK_STEP_SECONDS)
        runtime.led_driver.set_led_matrix(off_matrix)
        time.sleep(BOARD_CLEAR_REQUEST_BLINK_STEP_SECONDS)

    runtime.refresh_led_display()


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Run the Better Board Game single-player mode."
    )

    parser.add_argument(
        "--difficulty",
        type=parse_difficulty,
        default=Difficulty.MEDIUM,
        help="AI difficulty: easy, medium, or hard."
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
        "--scan-interval",
        type=float,
        default=0.05,
        help="Delay in seconds between scan-processing loops."
    )

    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    runtime = SinglePlayerRuntime(
        human_player=Player.RED,
        difficulty=args.difficulty,
        scanner_mode=args.scanner_mode,
        led_mode=args.led_mode
    )

    awaiting_board_clear_after_game_over = False

    print("Single-player runtime started.")
    print("Human player:", Player.RED)
    print("Difficulty:", args.difficulty)
    print("Scanner mode:", args.scanner_mode)
    print("LED mode:", args.led_mode)
    print("Scan interval:", args.scan_interval)
    print("Press Ctrl+C to stop.")

    try:
        while True:
            if awaiting_board_clear_after_game_over:
                stable_scan = runtime.read_stable_scan_matrix()

                if stable_scan is not None and scan_is_empty(stable_scan):
                    print("Board is empty after game over. Returning to menu.")
                    break

                time.sleep(POST_GAME_SCAN_INTERVAL_SECONDS)
                continue

            result = runtime.process_next_scan()

            if result is not None:
                print("Status:", result["status"])

                if result["error_code"] is not None:
                    print("Error:", result["error_code"])
                    print("Message:", result["message"])

                if result["pending_human_piece_removal"]:
                    print(
                        "Pending capture removals:",
                        result["pending_human_piece_removal"]
                    )

                state = result["state"]
                if state is not None and state.winner is not None:
                    print("Winner:", state.winner)
                    print("Game over detected. Remove all pieces to return to menu.")
                    blink_all_leds_for_board_clear_request(runtime)
                    awaiting_board_clear_after_game_over = True

            time.sleep(args.scan_interval)

    except KeyboardInterrupt:
        print("\nStopping single-player runtime.")

    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
