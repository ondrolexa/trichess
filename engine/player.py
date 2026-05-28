from engine.pieces import Bishop, King, Knight, Move, Pawn, Piece, Pos, Queen, Rook

# Direction vectors indexed by player pid (0=bottom, 1=left, 2=right).
# The "r" suffix on a direction code flips the vector sign.
STEP = {
    0: {
        "FL": 0 - 1j,
        "FR": 1 - 1j,
        "SL": -1 + 0j,
        "DF": 1 - 2j,
        "DL": -1 - 1j,
        "DR": 2 - 1j,
    },
    1: {
        "FL": 1 + 0j,
        "FR": 0 + 1j,
        "SL": 1 - 1j,
        "DF": 1 + 1j,
        "DL": 2 - 1j,
        "DR": -1 + 2j,
    },
    2: {
        "FL": -1 + 1j,
        "FR": -1 + 0j,
        "SL": 0 + 1j,
        "DF": -2 + 1j,
        "DL": -1 + 2j,
        "DR": -1 - 1j,
    },
}


class Player:
    """A class to represent a trichess player.

    Note:
        Player has defined position on trichessboard.
        0-bottom, 1-left, 2-right

    Args:
        pid (int): Player ID. Must be 0, 1 or 2 according to position

    Keyword Args:
        name (str, optional): Player name

    Attributes:
        pid (int): Player ID. Must be 0, 1 or 2 according to position
        name (str): Player name

    """

    def __init__(self, pid: int, **kwargs):
        self.pid = pid
        self.name = kwargs.get("name", f"Player {pid}")

    def __repr__(self) -> str:
        return f"[{self.name}]"

    def step(self, step) -> complex:
        """Convert a step code (eg "FL") to a complex direction vector.

        A trailing "r" negates the vector (reverse direction).
        """
        if step.endswith("r"):
            return -STEP[self.pid][step[:-1]]
        else:
            return STEP[self.pid][step]

    def pos_from_move(self, pos: Pos, move: Move) -> Pos:
        """Accumulate all step codes in a Move into a single position delta."""
        return pos.from_deltas([self.step(step) for step in move.steps], kind=move.kind)

    def pawn(self, **kwargs) -> Pawn:
        """Create Player's instance of pawn piece."""
        return Pawn(self, **kwargs)

    def knight(self, **kwargs) -> Knight:
        """Create Player's instance of knight piece."""
        return Knight(self, **kwargs)

    def bishop(self, **kwargs) -> Bishop:
        """Create Player's instance of bishop piece."""
        return Bishop(self, **kwargs)

    def rook(self, **kwargs) -> Rook:
        """Create Player's instance of rook piece."""
        return Rook(self, **kwargs)

    def queen(self, **kwargs) -> Queen:
        """Create Player's instance of queen piece."""
        return Queen(self, **kwargs)

    def king(self, **kwargs) -> King:
        """Create Player's instance of king piece."""
        # keep reference for king
        if not hasattr(self, "_king_piece"):
            self._king_piece = King(self, **kwargs)
        return self._king_piece

    @property
    def king_piece(self) -> King:
        return self._king_piece

    def promotion(self, label, **kwargs) -> Piece:
        match label:
            case "Q":
                return Queen(self, **kwargs)
            case "R":
                return Rook(self, **kwargs)
            case "B":
                return Bishop(self, **kwargs)
            case "N":
                return Knight(self, **kwargs)
