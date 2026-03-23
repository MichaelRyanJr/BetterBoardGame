from shared.constants import Player, Winner
from shared.game_state import AppliedMove, Coordinate, Move
from shared.move_validation import legal_moves_for_player, validate_move


def player_to_winner(player):
    """
    Convert a Player enum into the matching Winner enum.
    """
    if player == Player.RED:
        return Winner.RED
    else:
        return Winner.BLACK


def player_has_any_legal_moves(state, player):
    """
    Return True if the given player has at least one legal move.

    We clone the state here so we can safely adjust current_player and
    pending_multi_jump for the purpose of checking move availability.
    """

    temp_state = state.clone()
    temp_state.current_player = player

    # legal_moves_for_player() respects pending_multi_jump.
    # That is correct for the current player during a capture chain,
    # but when checking the OTHER player we should ignore that old
    # continuation requirement.
    if player != state.current_player:
        temp_state.pending_multi_jump = None

    legal_moves = legal_moves_for_player(temp_state, player)
    return len(legal_moves) > 0


def determine_winner_after_turn(state, next_player):
    """
    Determine whether the game is over after a turn finishes.

    This checks:
    1. whether either side has no pieces left
    2. whether the next player has any legal moves
    """

    red_count = state.count_pieces(Player.RED)
    black_count = state.count_pieces(Player.BLACK)

    if red_count == 0:
        return Winner.BLACK

    if black_count == 0:
        return Winner.RED

    if not player_has_any_legal_moves(state, next_player):
        return player_to_winner(next_player.get_opponent())

    return None


def build_applied_move(move, validation, next_player, winner, requires_continuation):
    """
    Build the AppliedMove object returned after a successful move.

    We create a normalized Move object here so the returned move contains
    the canonical captured_squares from validation.
    """

    normalized_move = Move(
        player=move.player,
        from_square=Coordinate(move.from_square.row, move.from_square.col),
        to_square=Coordinate(move.to_square.row, move.to_square.col),
        captured_squares=list(validation.captured_squares),
        promotion_requested=move.promotion_requested,
        sequence_id=move.sequence_id
    )

    return AppliedMove(
        move=normalized_move,
        captured_squares=list(validation.captured_squares),
        promoted=validation.promoted,
        next_player=next_player,
        winner=winner,
        requires_continuation=requires_continuation,
        continuation_square=validation.continuation_square
    )


def apply_validated_move(state, move, validation):
    """
    Apply a move that has already been validated as legal.

    This function mutates the GameState in place.
    """

    moving_piece = state.piece_at(move.from_square)

    # Remove the piece from its old location
    state.set_piece(move.from_square, None)

    # Remove any captured enemy pieces
    for captured_square in validation.captured_squares:
        state.set_piece(captured_square, None)

    # Promote if validation says this move should king the piece
    if validation.promoted:
        moving_piece.is_king = True

    # Place the piece in its new location
    state.set_piece(move.to_square, moving_piece)

    # version changes on every successfully applied move/jump
    state.version += 1

    # If another capture is required, the same player keeps moving
    if validation.continuation_square is not None:
        state.pending_multi_jump = validation.continuation_square
        state.winner = None

        applied_move = build_applied_move(
            move=move,
            validation=validation,
            next_player=state.current_player,
            winner=None,
            requires_continuation=True
        )
        return applied_move

    # Otherwise the turn is complete
    state.pending_multi_jump = None
    state.current_player = state.current_player.get_opponent()

    # move_number changes only when the turn fully passes
    state.move_number += 1

    winner = determine_winner_after_turn(state, state.current_player)
    state.winner = winner

    applied_move = build_applied_move(
        move=move,
        validation=validation,
        next_player=state.current_player,
        winner=winner,
        requires_continuation=False
    )
    return applied_move


def apply_move(state, move):
    """
    Validate and apply a move.

    Returns:
        (None, validation_result) if the move is illegal
        (applied_move, validation_result) if the move is legal

    This keeps the calling code simple:
        applied_move, result = apply_move(state, move)
        if not result.is_legal:
            handle_error(...)
    """

    validation = validate_move(state, move)

    if not validation.is_legal:
        return None, validation

    applied_move = apply_validated_move(state, move, validation)
    return applied_move, validation
