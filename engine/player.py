from engine.pieces import Bishop, King, Knight, Move, Pawn, Piece, Pos, Queen, Rook

# Direction vectors indexed by player pid (0=bottom, 1=left, 2=right).
# Stored as (dq, dr) tuples. Reverse directions included as "FLr" etc.
STEP = {
    0: {
        "FL": (0, -1),
        "FLr": (0, 1),
        "FR": (1, -1),
        "FRr": (-1, 1),
        "SL": (-1, 0),
        "SLr": (1, 0),
        "DF": (1, -2),
        "DFr": (-1, 2),
        "DL": (-1, -1),
        "DLr": (1, 1),
        "DR": (2, -1),
        "DRr": (-2, 1),
    },
    1: {
        "FL": (1, 0),
        "FLr": (-1, 0),
        "FR": (0, 1),
        "FRr": (0, -1),
        "SL": (1, -1),
        "SLr": (-1, 1),
        "DF": (1, 1),
        "DFr": (-1, -1),
        "DL": (2, -1),
        "DLr": (-2, 1),
        "DR": (-1, 2),
        "DRr": (1, -2),
    },
    2: {
        "FL": (-1, 1),
        "FLr": (1, -1),
        "FR": (-1, 0),
        "FRr": (1, 0),
        "SL": (0, 1),
        "SLr": (0, -1),
        "DF": (-2, 1),
        "DFr": (2, -1),
        "DL": (-1, 2),
        "DLr": (1, -2),
        "DR": (-1, -1),
        "DRr": (1, 1),
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

    def pos_from_move(self, pos: Pos, move: Move) -> Pos:
        """Accumulate all step codes in a Move into a single position delta."""
        pid = self.pid
        q, r = pos._q, pos._r
        for step in move.steps:
            dq, dr = STEP[pid][step]
            q += dq
            r += dr
        return Pos(q, r, kind=move.kind)

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
