"""Simple minimax implementation for the single-player AI."""

from shared.game_state import Coordinate, Move
from shared.move_validation import legal_moves_for_player
from shared.rules import apply_move

from ai.evaluator import evaluate_state


def candidate_action_to_move(player, action):
    """
    Convert a CandidateAction into the shared Move object.
    """

    captured_squares = []
    for square in action.captured_squares:
        captured_squares.append(Coordinate(square.row, square.col))

    return Move(
        player=player,
        from_square=Coordinate(action.from_square.row, action.from_square.col),
        to_square=Coordinate(action.to_square.row, action.to_square.col),
        captured_squares=captured_squares
    )


def build_ordering_key(move):
    """
    Build a deterministic ordering key so the AI behaves consistently.
    """

    is_capture = len(move.captured_squares) > 0

    return (
        0 if is_capture else 1,
        move.from_square.row,
        move.from_square.col,
        move.to_square.row,
        move.to_square.col
    )


def generate_legal_moves(state, player=None):
    if player is None:
        player = state.current_player

    candidate_actions = legal_moves_for_player(state, player)
    moves = []

    for action in candidate_actions:
        move = candidate_action_to_move(player, action)
        moves.append(move)

    moves.sort(key=build_ordering_key)
    return moves


def minimax_score(state, ai_player, depth, alpha, beta):
    legal_moves = generate_legal_moves(state, state.current_player)

    if depth == 0 or state.winner is not None or len(legal_moves) == 0:
        return evaluate_state(state, ai_player)

    maximizing = state.current_player == ai_player

    if maximizing:
        best_score = None

        for move in legal_moves:
            next_state = state.clone()
            applied_move, validation = apply_move(next_state, move)

            if not validation.is_legal:
                continue

            score = minimax_score(next_state, ai_player, depth - 1, alpha, beta)

            if best_score is None or score > best_score:
                best_score = score

            if alpha is None or score > alpha:
                alpha = score

            if beta is not None and alpha is not None and alpha >= beta:
                break

        if best_score is None:
            return evaluate_state(state, ai_player)

        return best_score

    best_score = None

    for move in legal_moves:
        next_state = state.clone()
        applied_move, validation = apply_move(next_state, move)

        if not validation.is_legal:
            continue

        score = minimax_score(next_state, ai_player, depth - 1, alpha, beta)

        if best_score is None or score < best_score:
            best_score = score

        if beta is None or score < beta:
            beta = score

        if alpha is not None and beta is not None and alpha >= beta:
            break

    if best_score is None:
        return evaluate_state(state, ai_player)

    return best_score


def choose_best_move(state, ai_player, depth):
    """
    Choose the best legal move for the AI player.

    Returns None if there are no legal moves.
    """

    legal_moves = generate_legal_moves(state, ai_player)

    if len(legal_moves) == 0:
        return None

    best_move = None
    best_score = None

    for move in legal_moves:
        next_state = state.clone()
        applied_move, validation = apply_move(next_state, move)

        if not validation.is_legal:
            continue

        score = minimax_score(next_state, ai_player, depth - 1, None, None)

        if best_move is None:
            best_move = move
            best_score = score
            continue

        if score > best_score:
            best_move = move
            best_score = score

    return best_move
