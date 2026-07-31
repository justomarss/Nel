import random
import time


def run(nel):

    while True:

        nel.state.energy = max(0, nel.state.energy - 1)

        nel.state.boredom = min(100, nel.state.boredom + 1)

        if random.random() < 0.2:
            nel.state.curiosity += 1

        nel.think()

        print("----------------")

        time.sleep(5)