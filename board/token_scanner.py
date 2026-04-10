from shared.constants import BOARD_SIZE


def empty_scan_matrix():
    """Build a blank 8x8 occupancy matrix."""
    matrix = []

    for _ in range(BOARD_SIZE):
        row = []
        for _ in range(BOARD_SIZE):
            row.append(False)
        matrix.append(row)

    return matrix


def clone_scan_matrix(scan_matrix):
    """Return a deep copy of an 8x8 occupancy matrix."""
    cloned_matrix = []

    for row in scan_matrix:
        cloned_row = []

        for value in row:
            cloned_row.append(bool(value))

        cloned_matrix.append(cloned_row)

    return cloned_matrix


def normalize_scan_matrix(scan_matrix):
    """Validate and normalize scan data into an 8x8 boolean matrix."""
    if len(scan_matrix) != BOARD_SIZE:
        raise ValueError("scan_matrix must have exactly 8 rows.")

    normalized_matrix = []

    for row_index, row in enumerate(scan_matrix):
        if len(row) != BOARD_SIZE:
            raise ValueError(
                "scan_matrix row " + str(row_index) + " must have exactly 8 columns."
            )

        normalized_row = []

        for value in row:
            normalized_row.append(bool(value))

        normalized_matrix.append(normalized_row)

    return normalized_matrix


class TokenScanner:
    """
    Read board occupancy as an 8x8 boolean matrix.

    For now this class runs in mock mode.
    Later, the GPIO scanning code can replace the internal read logic
    without changing the rest of the board-side API.
    """

    def __init__(
        self,
        mode="mock",
        stable_reads_required=2,
        initial_scan_matrix=None
    ):
        if stable_reads_required < 1:
            raise ValueError("stable_reads_required must be at least 1.")

        self.mode = mode
        self.stable_reads_required = stable_reads_required

        if initial_scan_matrix is None:
            self.mock_scan_matrix = empty_scan_matrix()
        else:
            self.mock_scan_matrix = normalize_scan_matrix(initial_scan_matrix)

        self.mock_scan_sequence = []
        self.mock_sequence_index = 0

        self.latest_scan_matrix = None
        self.previous_scan_matrix = None
        self.matching_scan_count = 0

    def set_mock_scan_matrix(self, scan_matrix):
        """Replace the current mock scan matrix."""
        self.mock_scan_matrix = normalize_scan_matrix(scan_matrix)
        self.mock_scan_sequence = []
        self.mock_sequence_index = 0

    def set_mock_scan_sequence(self, scan_sequence):
        """
        Load a sequence of mock scans.

        Each call to read_scan_matrix() will move forward in the sequence.
        Once the end is reached, the last matrix will keep repeating.
        """
        if len(scan_sequence) == 0:
            raise ValueError("scan_sequence must contain at least one matrix.")

        normalized_sequence = []

        for scan_matrix in scan_sequence:
            normalized_sequence.append(normalize_scan_matrix(scan_matrix))

        self.mock_scan_sequence = normalized_sequence
        self.mock_sequence_index = 0

    def reset_stability_tracking(self):
        """Forget the previous scan history used for stability checks."""
        self.previous_scan_matrix = None
        self.matching_scan_count = 0

    def _read_mock_scan_matrix(self):
        """Return the next mock scan matrix."""
        if len(self.mock_scan_sequence) > 0:
            current_matrix = self.mock_scan_sequence[self.mock_sequence_index]

            if self.mock_sequence_index < len(self.mock_scan_sequence) - 1:
                self.mock_sequence_index += 1

            return clone_scan_matrix(current_matrix)

        return clone_scan_matrix(self.mock_scan_matrix)

    def _read_gpio_scan_matrix(self):
        """
        Placeholder for the future real GPIO implementation.

        The public scanner API is already defined now.
        Later, the row/column scanning code can go here.
        """
        raise NotImplementedError(
            "GPIO token scanning has not been implemented yet."
        )

    def _read_raw_scan_matrix(self):
        """Read one raw scan from the active scanner mode."""
        if self.mode == "mock":
            return self._read_mock_scan_matrix()

        if self.mode == "gpio":
            return self._read_gpio_scan_matrix()

        raise ValueError("Unsupported scanner mode: " + str(self.mode))

    def read_scan_matrix(self):
        """
        Read one scan and return it as an 8x8 boolean matrix.

        This always returns the latest raw reading, even if the scan
        is not stable yet.
        """
        current_scan = self._read_raw_scan_matrix()
        current_scan = normalize_scan_matrix(current_scan)

        if self.previous_scan_matrix is None:
            self.matching_scan_count = 1
        elif current_scan == self.previous_scan_matrix:
            self.matching_scan_count += 1
        else:
            self.matching_scan_count = 1

        self.previous_scan_matrix = clone_scan_matrix(current_scan)
        self.latest_scan_matrix = clone_scan_matrix(current_scan)

        return clone_scan_matrix(current_scan)

    def read_stable_scan_matrix(self):
        """
        Read one scan and return it only if it is stable.

        A scan is considered stable when the same matrix has been read
        stable_reads_required times in a row.
        """
        current_scan = self.read_scan_matrix()

        if self.matching_scan_count >= self.stable_reads_required:
            return clone_scan_matrix(current_scan)

        return None

    def get_latest_scan_matrix(self):
        """Return the latest scan that was read, or None if no scan exists yet."""
        if self.latest_scan_matrix is None:
            return None

        return clone_scan_matrix(self.latest_scan_matrix)

    def get_matching_scan_count(self):
        """Return how many times the current scan has repeated in a row."""
        return self.matching_scan_count

    def is_current_scan_stable(self):
        """Return True if the latest scan is currently considered stable."""
        if self.latest_scan_matrix is None:
            return False

        return self.matching_scan_count >= self.stable_reads_required

    def shutdown(self):
        """
        Clean up scanner resources.

        This does not need to do anything in mock mode, but keeping the
        method now makes later GPIO cleanup easier.
        """
        return
