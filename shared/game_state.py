from dataclasses import dataclass, field
from copy import deepcopy
from uuid import uuid4

from shared.constants import BOARD_SIZE, GameMode, Player, Winner, is_dark_square

# Represents one board location using row and column
@dataclass
class Coordinate:
    row: int
    col: int

    def to_dict(self):
        return {
            "row": self.row,
            "col": self.col
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            row=data["row"],
            col=data["col"]
        )

# Stores which player owns the piece and whether it is a king
@dataclass
class Piece:
    owner: Player
    is_king: bool = False

    def to_dict(self):
        return {
            "owner": self.owner.value,
            "is_king": self.is_king
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            owner=Player(data["owner"]),
            is_king=bool(data.get("is_king", False))
        )

# Represents a requested move from one square to another
@dataclass
class Move:
    player: Player
    from_square: Coordinate
    to_square: Coordinate
    # captured_squares stores any jumped enemy pieces
    captured_squares: list = field(default_factory=list)
    promotion_requested: bool = False
    sequence_id: int = None

    def to_dict(self):
        captured_list = []
        for square in self.captured_squares:
            captured_list.append(square.to_dict())

        return {
            "player": self.player.value,
            "from_square": self.from_square.to_dict(),
            "to_square": self.to_square.to_dict(),
            "captured_squares": captured_list,
            "promotion_requested": self.promotion_requested,
            "sequence_id": self.sequence_id
        }

    @classmethod
    def from_dict(cls, data):
        captured_list = []
        for square in data.get("captured_squares", []):
            captured_list.append(Coordinate.from_dict(square))

        return cls(
            player=Player(data["player"]),
            from_square=Coordinate.from_dict(data["from_square"]),
            to_square=Coordinate.from_dict(data["to_square"]),
            captured_squares=captured_list,
            promotion_requested=bool(data.get("promotion_requested", False)),
            sequence_id=data.get("sequence_id")
        )

# Stores the result after a move is successfully applied
@dataclass
class AppliedMove:
    move: Move
    captured_squares: list = field(default_factory=list)
    promoted: bool = False
    next_player: Player = None
    winner: Winner = None
    requires_continuation: bool = False
    continuation_square: Coordinate = None

# Stores the full board and all game status information
@dataclass
class GameState:
    board: list
    current_player: Player = Player.BLACK
    mode: GameMode = GameMode.MULTIPLAYER
    winner: Winner = None
    move_number: int = 1
    version: int = 0
    # pending_multi_jump is used when a piece must continue capturing
    pending_multi_jump: Coordinate = None
    game_id: str = field(default_factory=lambda: "game-" + uuid4().hex[:12])
    session_id: str = field(default_factory=lambda: "session-" + uuid4().hex[:12])
    metadata: dict = field(default_factory=dict)

    def clone(self):
        return GameState(
            board=deepcopy(self.board),
            current_player=self.current_player,
            mode=self.mode,
            winner=self.winner,
            move_number=self.move_number,
            version=self.version,
            pending_multi_jump=self.pending_multi_jump,
            game_id=self.game_id,
            session_id=self.session_id,
            metadata=deepcopy(self.metadata)
        )
        
    # Returns the piece at a specific board coordinate
    def piece_at(self, square):
        return self.board[square.row][square.col]

    # Places a piece or None at a specific board coordinate
    def set_piece(self, square, piece):
        self.board[square.row][square.col] = piece

    def count_pieces(self, owner):
        count = 0
        for row in self.board:
            for piece in row:
                if piece is not None and piece.owner == owner:
                    count += 1
        return count

    # Creates a fresh empty 8x8 board
    @staticmethod
    def empty_board():
        board = []
        for row in range(BOARD_SIZE):
            current_row = []
            for col in range(BOARD_SIZE):
                current_row.append(None)
            board.append(current_row)
        return board

    # Creates the standard starting board for a new game
    @classmethod
    def initial(cls, mode=GameMode.MULTIPLAYER):
        board = cls.empty_board()

        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if not is_dark_square(row, col):
                    continue

                if row < 3:
                    board[row][col] = Piece(owner=Player.BLACK)
                elif row >= BOARD_SIZE - 3:
                    board[row][col] = Piece(owner=Player.RED)

        return cls(
            board=board,
            current_player=Player.BLACK,
            mode=mode
        )

    # Converts the game state into a dictionary to send over the internet
    def to_dict(self):
        serialized_board = []

        for row in self.board:
            serialized_row = []
            for piece in row:
                if piece is None:
                    serialized_row.append(None)
                else:
                    serialized_row.append(piece.to_dict())
            serialized_board.append(serialized_row)

        if self.winner is None:
            winner_value = None
        else:
            winner_value = self.winner.value

        if self.pending_multi_jump is None:
            pending_value = None
        else:
            pending_value = self.pending_multi_jump.to_dict()

        return {
            "board": serialized_board,
            "current_player": self.current_player.value,
            "mode": self.mode.value,
            "winner": winner_value,
            "move_number": self.move_number,
            "version": self.version,
            "pending_multi_jump": pending_value,
            "game_id": self.game_id,
            "session_id": self.session_id,
            "metadata": deepcopy(self.metadata)
        }

    # Rebuilds a game state object from dictionary data created in method above
    @classmethod
    def from_dict(cls, data):
        board = []

        for row in data["board"]:
            new_row = []
            for piece in row:
                if piece is None:
                    new_row.append(None)
                else:
                    new_row.append(Piece.from_dict(piece))
            board.append(new_row)

        if data.get("winner") is None:
            winner_value = None
        else:
            winner_value = Winner(data["winner"])

        if data.get("pending_multi_jump") is None:
            pending_value = None
        else:
            pending_value = Coordinate.from_dict(data["pending_multi_jump"])

        return cls(
            board=board,
            current_player=Player(data["current_player"]),
            mode=GameMode(data["mode"]),
            winner=winner_value,
            move_number=int(data.get("move_number", 1)),
            version=int(data.get("version", 0)),
            pending_multi_jump=pending_value,
            game_id=data.get("game_id", "game-" + uuid4().hex[:12]),
            session_id=data.get("session_id", "session-" + uuid4().hex[:12]),
            metadata=deepcopy(data.get("metadata", {}))
        )
