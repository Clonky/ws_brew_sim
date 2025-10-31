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