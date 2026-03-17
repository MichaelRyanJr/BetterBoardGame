"""Shared constants, enums, and helper functions for the game."""

from enum import Enum

# Standard checkers board dimensions
BOARD_SIZE = 8
STARTING_ROWS_PER_SIDE = 3
TOTAL_STARTING_PIECES_PER_SIDE = 12

# Simple LED states for the physical board
LED_OFF = 0
LED_ON = 1


class Player(str, Enum):
    RED = "red"
    BLACK = "black"

    def get_opponent(self):
        if self == Player.RED:
            return Player.BLACK
        else:
            return Player.RED

    def get_forward_row_delta(self):
        # In the matrix, row number increases as it goes down.
        # Player.RED starts near the bottom and moves upward.
        if self == Player.RED:
            return -1
        else:
            return 1


class GameMode(str, Enum):
    MULTIPLAYER = "multiplayer"
    SINGLE_PLAYER = "single_player"


class ErrorCode(str, Enum):
    OUT_OF_TURN = "out_of_turn"
    INVALID_MODE = "invalid_mode"
    SOURCE_EMPTY = "source_empty"
    NOT_YOUR_PIECE = "not_your_piece"
    DESTINATION_OCCUPIED = "destination_occupied"
    OUT_OF_BOUNDS = "out_of_bounds"
    INVALID_SQUARE = "invalid_square"
    ILLEGAL_DIRECTION = "illegal_direction"
    ILLEGAL_DISTANCE = "illegal_distance"
    MUST_CAPTURE = "must_capture"
    BACKWARD_NON_KING = "backward_non_king"
    MISSING_CAPTURE_REMOVAL = "missing_capture_removal"
    AMBIGUOUS_SCAN = "ambiguous_scan"
    DESYNC = "desync"
    CONNECTION_LOST = "connection_lost"
    SERVER_REJECTED_STATE = "server_rejected_state"
    MULTI_JUMP_REQUIRED = "multi_jump_required"


class EventType(str, Enum):
    SCAN_SNAPSHOT = "scan_snapshot"
    STABLE_SCAN = "stable_scan"
    CANDIDATE_MOVE = "candidate_move"
    STATE_SYNC = "state_sync"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    DESYNC_DETECTED = "desync_detected"
    PIECE_REMOVED_REQUIRED = "piece_removed_required"
    ILLEGAL_STATE_DETECTED = "illegal_state_detected"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Winner(str, Enum):
    RED = "red"
    BLACK = "black"
    DRAW = "draw"


def is_dark_square(row, col):
    """Return True if the square is a playable dark square."""
    return (row + col) % 2 == 1 # row + col of dark squares will always be odd
