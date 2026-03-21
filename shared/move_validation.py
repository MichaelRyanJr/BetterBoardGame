from dataclasses import dataclass, field

from shared.constants import BOARD_SIZE, ErrorCode, Player, is_dark_square
from shared.game_state import Coordinate, GameState, Move, Piece

# Object that gives the final result of the validation check
@dataclass
class ValidationResult:
    is_legal: bool
    error_code: ErrorCode = None
    message: str = ""
    captured_squares: list = field(default_factory=list)
    promoted: bool = False
    continuation_square: Coordinate = None

# Object that lists the possible moves from a specific piece
@dataclass
class CandidateAction:
    from_square: Coordinate
    to_square: Coordinate
    captured_squares: list = field(default_factory=list)

    def is_capture(self):
        return len(self.captured_squares) > 0

# Checks if a coordinate is actually inside the boards coordinates
def within_bounds(square):
    if square.row < 0 or square.row >= BOARD_SIZE:
        return False
    if square.col < 0 or square.col >= BOARD_SIZE:
        return False
    return True

# Returns the directions a piece is legally allowed to move relative to the coordinate grid (king can do either, normal red = [-1], normal black = [1])
def get_movement_directions(piece):
    if piece.is_king:
        return [-1, 1]
    else:
        return [piece.owner.get_forward_row_delta()]

# checks if a move would result in a piece becoming a king
def move_would_promote(piece, destination):
    if piece.is_king:
        return False

    if piece.owner == Player.RED and destination.row == 0:
        return True

    if piece.owner == Player.BLACK and destination.row == BOARD_SIZE - 1:
        return True

    return False

# Finds all of the moves that a piece can make that dont result in a capture
def piece_simple_moves(state, source):
    piece = state.piece_at(source)

    if piece is None:
        return []

    moves = []
    row_directions = get_movement_directions(piece)

    for row_delta in row_directions:
        for col_delta in [-1, 1]:
            destination = Coordinate(
                row=source.row + row_delta,
                col=source.col + col_delta
            )

            if not within_bounds(destination):
                continue

            if not is_dark_square(destination.row, destination.col):
                continue

            if state.piece_at(destination) is None:
                action = CandidateAction(
                    from_square=source,
                    to_square=destination
                )
                moves.append(action)

    return moves

# returns the moves a piece can make that result in an enemy piece being captured
def piece_capture_moves(state, source):
    piece = state.piece_at(source)

    if piece is None:
        return []

    captures = []
    row_directions = get_movement_directions(piece)

    for row_delta in row_directions:
        for col_delta in [-1, 1]:
            jumped_square = Coordinate(
                row=source.row + row_delta,
                col=source.col + col_delta
            )

            landing_square = Coordinate(
                row=source.row + 2 * row_delta,
                col=source.col + 2 * col_delta
            )

            if not within_bounds(jumped_square):
                continue

            if not within_bounds(landing_square):
                continue

            if not is_dark_square(landing_square.row, landing_square.col):
                continue

            jumped_piece = state.piece_at(jumped_square)

            if jumped_piece is None:
                continue

            if jumped_piece.owner == piece.owner:
                continue

            if state.piece_at(landing_square) is not None:
                continue

            action = CandidateAction(
                from_square=source,
                to_square=landing_square,
                captured_squares=[jumped_square]
            )
            captures.append(action)

    return captures

# Scans all pieces for a player to see if there is a capture possible, used to enforce the "if any captures exist, player must capture" rule
def all_capture_moves(state, player):
    captures = []

    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            square = Coordinate(row, col)
            piece = state.piece_at(square)

            if piece is None:
                continue

            if piece.owner != player:
                continue

            piece_captures = piece_capture_moves(state, square)
            for capture in piece_captures:
                captures.append(capture)

    return captures

#Gets every legal move that a player could make, if player is jumping multiple pieces it ensures they can only continue to move that piece, also ensures if theres a capture available it only returns possible captures
def legal_moves_for_player(state, player=None):
    if player is None:
        player = state.current_player

    if state.pending_multi_jump is not None:
        return piece_capture_moves(state, state.pending_multi_jump)

    captures = all_capture_moves(state, player)

    if len(captures) > 0:
        return captures

    moves = []

    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            square = Coordinate(row, col)
            piece = state.piece_at(square)

            if piece is None:
                continue

            if piece.owner != player:
                continue

            piece_moves = piece_simple_moves(state, square)
            for move in piece_moves:
                moves.append(move)

    return moves

# Used to check the state of the game after a move without changing the actual state
def simulate_piece_after_move(piece, destination):
    new_piece = Piece(
        owner=piece.owner,
        is_king=piece.is_king
    )

    if move_would_promote(piece, destination):
        new_piece.is_king = True

    return new_piece

# simulates a jump then checks for a forced multi jump
def additional_captures_after_move(state, source, destination, captured_squares):
    temp_state = state.clone()

    moving_piece = temp_state.piece_at(source)
    if moving_piece is None:
        return []

    temp_state.set_piece(source, None)

    for square in captured_squares:
        temp_state.set_piece(square, None)

    updated_piece = simulate_piece_after_move(moving_piece, destination)
    temp_state.set_piece(destination, updated_piece)

    return piece_capture_moves(temp_state, destination)

# Main function, checks in the following order: (Note: many of these checks are not possible in multiplayer, but im unsure if the AI will need them so I implemented them anyways)
# 1) Is the game already over
# 2) Ensures the player whos turn it is was the one to move
# 3) Checks to ensure the coordinates are actually a possible coordinate (inside the 8x8)
# 4) Ensures the piece's coordinates were moved to a dark square
# 5) Checks to that the source tile actually contains a piece
# 6) Ensures that piece actually belongs to the player moving it
# 7) Ensures the destination square is empty
# 8) Checks to see if the player must keep moving if a multijump is possible
# 9) Ensures the move is on a diagonal
# 10) Makes sure the move is not more than one diagonal (if not a multijump)
# 11) If a piece is not a king, it checks for backwards movement
# 12) Enforces madatory capture rule if available
# 13) Checks to make sure the piece being captured is actually an enemy
# 14) Checks to see if the player is required to multijump
# 15) Finally, if none of these rules are broken it returns that the move was valid
def validate_move(state, move):
    if state.winner is not None:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.SERVER_REJECTED_STATE,
            message="Game is already over."
        )

    if move.player != state.current_player:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.OUT_OF_TURN,
            message="It is not this player's turn."
        )

    if not within_bounds(move.from_square) or not within_bounds(move.to_square):
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.OUT_OF_BOUNDS,
            message="Move coordinates are outside the board."
        )

    if not is_dark_square(move.from_square.row, move.from_square.col):
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.INVALID_SQUARE,
            message="Source square is not playable."
        )

    if not is_dark_square(move.to_square.row, move.to_square.col):
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.INVALID_SQUARE,
            message="Destination square is not playable."
        )

    piece = state.piece_at(move.from_square)

    if piece is None:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.SOURCE_EMPTY,
            message="There is no piece on the source square."
        )

    if piece.owner != move.player:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.NOT_YOUR_PIECE,
            message="That piece belongs to the other player."
        )

    if state.piece_at(move.to_square) is not None:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.DESTINATION_OCCUPIED,
            message="Destination square is already occupied."
        )

    if state.pending_multi_jump is not None:
        if move.from_square != state.pending_multi_jump:
            return ValidationResult(
                is_legal=False,
                error_code=ErrorCode.MULTI_JUMP_REQUIRED,
                message="The same piece must continue the capture chain."
            )

    row_delta = move.to_square.row - move.from_square.row
    col_delta = move.to_square.col - move.from_square.col

    abs_row = abs(row_delta)
    abs_col = abs(col_delta)

    if abs_row != abs_col:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.ILLEGAL_DIRECTION,
            message="Moves must be diagonal."
        )

    if abs_row != 1 and abs_row != 2:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.ILLEGAL_DISTANCE,
            message="Moves must go one square or one jump."
        )

    if not piece.is_king:
        expected_row_change = piece.owner.get_forward_row_delta() * abs_row
        if row_delta != expected_row_change:
            return ValidationResult(
                is_legal=False,
                error_code=ErrorCode.BACKWARD_NON_KING,
                message="Non-king pieces cannot move backward."
            )

    forced_captures = all_capture_moves(state, move.player)
    must_capture = len(forced_captures) > 0

    if abs_row == 1:
        if state.pending_multi_jump is not None:
            return ValidationResult(
                is_legal=False,
                error_code=ErrorCode.MULTI_JUMP_REQUIRED,
                message="A capture continuation is required."
            )

        if must_capture:
            return ValidationResult(
                is_legal=False,
                error_code=ErrorCode.MUST_CAPTURE,
                message="A capture is available and must be taken."
            )

        return ValidationResult(
            is_legal=True,
            captured_squares=[],
            promoted=move_would_promote(piece, move.to_square),
            continuation_square=None
        )

    jumped_square = Coordinate(
        row=(move.from_square.row + move.to_square.row) // 2,
        col=(move.from_square.col + move.to_square.col) // 2
    )

    jumped_piece = state.piece_at(jumped_square)

    if jumped_piece is None:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.ILLEGAL_DISTANCE,
            message="Capture jump must go over an opposing piece."
        )

    if jumped_piece.owner == piece.owner:
        return ValidationResult(
            is_legal=False,
            error_code=ErrorCode.ILLEGAL_DISTANCE,
            message="You cannot jump over your own piece."
        )

    if len(move.captured_squares) > 0:
        if len(move.captured_squares) != 1 or move.captured_squares[0] != jumped_square:
            return ValidationResult(
                is_legal=False,
                error_code=ErrorCode.SERVER_REJECTED_STATE,
                message="Captured square data does not match the actual jump."
            )

    promoted = move_would_promote(piece, move.to_square)
    continuation_square = None

    if not promoted:
        next_captures = additional_captures_after_move(
            state,
            move.from_square,
            move.to_square,
            [jumped_square]
        )

        if len(next_captures) > 0:
            continuation_square = move.to_square

    return ValidationResult(
        is_legal=True,
        captured_squares=[jumped_square],
        promoted=promoted,
        continuation_square=continuation_square
    ) 
