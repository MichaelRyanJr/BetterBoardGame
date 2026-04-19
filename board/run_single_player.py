import argparse
import time

from board.single_player_runtime import SinglePlayerRuntime
from shared.constants import Difficulty, Player


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
        human_player=Player.BLACK,
        difficulty=args.difficulty,
        scanner_mode=args.scanner_mode,
        led_mode=args.led_mode
    )

    print("Single-player runtime started.")
    print("Human player:", Player.BLACK)
    print("Difficulty:", args.difficulty)
    print("Scanner mode:", args.scanner_mode)
    print("LED mode:", args.led_mode)
    print("Scan interval:", args.scan_interval)
    print("Press Ctrl+C to stop.")

    try:
        while True:
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

            time.sleep(args.scan_interval)

    except KeyboardInterrupt:
        print("\nStopping single-player runtime.")

    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
