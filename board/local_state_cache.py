from shared.game_state import GameState


class LocalStateCache:
    def __init__(self, initial_state=None):
        # Store the cached state here. Start empty unless one is provided.
        self.state = None

        if initial_state is not None:
            # Store a clone so outside code cannot accidentally modify the cache.
            self.state = initial_state.clone()

    def has_state(self):
        # Return True if a state is currently stored.
        return self.state is not None

    def clear(self):
        # Remove the stored state.
        self.state = None

    def get_state(self):
        # Return a clone so callers do not directly modify the cached copy.
        if self.state is None:
            return None

        return self.state.clone()

    def get_version(self):
        # Return the version number of the cached state.
        if self.state is None:
            return None

        return self.state.version

    def set_state(self, new_state):
        # Replace the cached state directly.
        self.state = new_state.clone()

    def should_accept_state(self, new_state):
        # Always accept the first state we receive.
        if self.state is None:
            return True

        # If the game or session changed, treat it as a different state stream.
        same_game_id = new_state.game_id == self.state.game_id
        same_session_id = new_state.session_id == self.state.session_id

        if not same_game_id or not same_session_id:
            return True

        # For the same game/session, only accept newer versions.
        if new_state.version > self.state.version:
            return True

        return False

    def update_if_newer(self, new_state):
        # Update the cache only when the new state should replace the old one.
        if self.should_accept_state(new_state):
            self.state = new_state.clone()
            return True

        return False
