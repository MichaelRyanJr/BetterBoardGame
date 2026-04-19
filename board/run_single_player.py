import time

from board.single_player_runtime import SinglePlayerRuntime
from shared.constants import Difficulty, Player


def main():
    # Change these if you want different defaults.
    human_player = Player.BLACK
    difficulty = Difficulty.MEDIUM

    # Use the real board hardware by default.
    scanner_mode = "gpio"
    led_mode = "hardware"

    # Helpful while developing on a non-hardware machine:
    # scanner_mode = "mock"
    # led_mode = "mock"

    runtime = SinglePlayerRuntime(
        human_player=human_player,
        difficulty=difficulty,
        scanner_mode=scanner_mode,
        led_mode=led_mode
    )

    print("Single-player runtime started.")
    print("Human player:", human_player)
    print("Difficulty:", difficulty)
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

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopping single-player runtime.")

    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
