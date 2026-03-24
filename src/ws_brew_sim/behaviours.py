import random
import time


class Behaviour:
    def __init__(self, initial_state):
        self.state = initial_state

    def update(self):
        pass


class NormalDistBehaviour(Behaviour):
    def __init__(self, initial_state, stddev):
        self.mean = initial_state
        self.stddev = stddev

    def update(self):
        new_val = random.gauss(self.mean, self.stddev)
        self.state = new_val

class StaticBehaviour(Behaviour):
    def __init__(self, initial_state):
        super().__init__(initial_state)

    def update(self):
        pass

class DurationTimer(Behaviour):

    def __init__(self, duration: float = 0.0):
        super().__init__(initial_state=duration)
        self.last_update_time = time.time()

    def update(self):
        current_time = time.time()
        elapsed_time = current_time - self.last_update_time
        self.state += elapsed_time
        self.last_update_time = current_time


class ConditionalDurationTimer(Behaviour):
    """Accumulates elapsed time in milliseconds only when condition() returns True.

    last_update_time is always refreshed so no time-jump occurs when the
    condition transitions from False to True.
    """

    def __init__(self, duration_ms: float = 0.0, condition=None):
        super().__init__(initial_state=duration_ms)
        self.last_update_time = time.time()
        self.condition = condition

    def update(self):
        current_time = time.time()
        elapsed_ms = (current_time - self.last_update_time) * 1000
        self.last_update_time = current_time
        if self.condition is None or self.condition():
            self.state += elapsed_ms