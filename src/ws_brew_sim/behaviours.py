import random


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