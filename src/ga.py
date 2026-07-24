import copy
import heapq
import metrics
import multiprocessing.pool as mpool
import os
import random
import shutil
import time
import math

width = 200
height = 16

options = [
    "-",  # an empty space
    "X",  # a solid wall
    "?",  # a question mark block with a coin
    "M",  # a question mark block with a mushroom
    "B",  # a breakable block
    "o",  # a coin
    "|",  # a pipe segment
    "T",  # a pipe top
    "E",  # an enemy
    #"f",  # a flag, do not generate
    #"v",  # a flagpole, do not generate
    #"m"  # mario's start position, do not generate
]

# The level as a grid of tiles


class Individual_Grid(object):
    __slots__ = ["genome", "_fitness"]

    def __init__(self, genome):
        self.genome = copy.deepcopy(genome)
        self._fitness = None

    # Update this individual's estimate of its fitness.
    # This can be expensive so we do it once and then cache the result.
    def calculate_fitness(self):
        measurements = metrics.metrics(self.to_level())
        # Print out the possible measurements or look at the implementation of metrics.py for other keys:
        # print(measurements.keys())
        # Default fitness function: Just some arbitrary combination of a few criteria.  Is it good?  Who knows?
        # STUDENT Modify this, and possibly add more metrics.  You can replace this with whatever code you like.
        coefficients = dict(
            meaningfulJumpVariance=0.5,
            negativeSpace=0.6,
            pathPercentage=0.5,
            emptyPercentage=0.6,
            linearity=-0.5,
            solvability=2.0
            meaningfulJumps=0.4
            decorationPercentage=0.3
        )
        self._fitness = sum(map(lambda m: coefficients[m] * measurements[m],
                                coefficients))
        return self

    # Return the cached fitness value or calculate it as needed.
    def fitness(self):
        if self._fitness is None:
            self.calculate_fitness()
        return self._fitness

    # Mutate a genome into a new genome.  Note that this is a _genome_, not an individual!
    def mutate(self, genome):
        mutation_rate = 0.03

        for x in range(1, width-1):

            if random.random() < mutation_rate:

                # remove old object
                for y in range(1,height-1):
                    if genome[y][x] != "m" and genome[y][x] not in ["f","v"]:
                        genome[y][x] = "-"


                choice = random.random()


                # create block
                if choice < 0.35:
                    y = random.randint(8,13)
                    genome[y][x] = random.choice(["X","B","?"])


                # create coin
                elif choice < 0.55:
                    y = random.randint(5,10)
                    genome[y][x] = "o"


                # create enemy
                elif choice < 0.75:
                    genome[14][x] = "E"


                # create pipe
                else:
                    pipe_height = random.randint(2,5)

                    genome[15-pipe_height][x] = "T"

                    for y in range(16-pipe_height,15):
                        genome[y][x] = "|"


        return genome

    # Create zero or more children from self and other
        # Create zero or more children from self and other
    def generate_children(self, other):

        new_genome = copy.deepcopy(self.genome)


        # Column crossover instead of tile crossover
        for x in range(1, width - 1):

            if random.random() < 0.5:

                for y in range(height):
                    new_genome[y][x] = other.genome[y][x]


        # mutation
        new_genome = self.mutate(new_genome)


        # repair level
        for x in range(width):

            # always keep floor
            new_genome[15][x] = "X"


            # remove floating enemies
            if new_genome[14][x] == "E":
                if new_genome[15][x] != "X":
                    new_genome[14][x] = "-"


            # remove floating blocks
            for y in range(1,14):

                if new_genome[y][x] in ["X","B","?"]:

                    if all(
                        new_genome[y2][x] == "-"
                        for y2 in range(y+1,15)
                    ):
                        new_genome[y][x] = "-"


        return (Individual_Grid(new_genome),)

    # Turn the genome into a level string (easy for this genome)
    def to_level(self):
        return self.genome

    # These both start with every floor tile filled with Xs
    # STUDENT Feel free to change these
    @classmethod
    def empty_individual(cls):
        g = [["-" for col in range(width)] for row in range(height)]
        g[15][:] = ["X"] * width
        g[14][0] = "m"
        g[7][-1] = "v"
        for row in range(8, 14):
            g[row][-1] = "f"
        for col in range(14, 16):
            g[col][-1] = "X"
        return cls(g)

    @classmethod
    def random_individual(cls):

        g = [["-" for col in range(width)] for row in range(height)]


        # floor
        g[15][:] = ["X"] * width


        # mario
        g[14][0] = "m"


        # flag
        g[7][-1] = "v"

        for row in range(8,14):
            g[row][-1] = "f"


        for x in range(5,width-5):

            chance = random.random()


            # enemy
            if chance < 0.10:

                g[14][x] = "E"


            # pipe
            elif chance < 0.18:

                h = random.randint(2,4)

                g[15-h][x] = "T"

                for y in range(16-h,15):
                    g[y][x] = "|"


            # block structure
            elif chance < 0.35:

                amount = random.randint(1,3)

                for i in range(amount):

                    if x+i < width-1:
                        g[13-i][x+i] = random.choice([
                            "X",
                            "B",
                            "?"
                        ])


            # coins
            elif chance < 0.55:

                y = random.randint(7,11)
                g[y][x] = "o"


        # goal protection
        g[14][-1] = "X"
        g[15][-1] = "X"


        return cls(g)


def offset_by_upto(val, variance, min=None, max=None):
    val += random.normalvariate(0, variance**0.5)
    if min is not None and val < min:
        val = min
    if max is not None and val > max:
        val = max
    return int(val)


def clip(lo, val, hi):
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val

# Inspired by https://www.researchgate.net/profile/Philippe_Pasquier/publication/220867545_Towards_a_Generic_Framework_for_Automated_Video_Game_Level_Creation/links/0912f510ac2bed57d1000000.pdf


class Individual_DE(object):
    # Calculating the level isn't cheap either so we cache it too.
    __slots__ = ["genome", "_fitness", "_level"]

    # Genome is a heapq of design elements sorted by X, then type, then other parameters
    def __init__(self, genome):
        self.genome = list(genome)
        heapq.heapify(self.genome)
        self._fitness = None
        self._level = None

    # Calculate and cache fitness
    def calculate_fitness(self):
        measurements = metrics.metrics(self.to_level())
        # Default fitness function: Just some arbitrary combination of a few criteria.  Is it good?  Who knows?
        # STUDENT Add more metrics?
        # STUDENT Improve this with any code you like
        coefficients = dict(
            meaningfulJumpVariance=1.5,
            negativeSpace=1.0,
            pathPercentage=2.0,
            emptyPercentage=0.2,
            linearity=-0.2,
            solvability=5.0
        )
        penalties = 0
        # STUDENT For example, too many stairs are unaesthetic.  Let's penalize that
        if len(list(filter(lambda de: de[1] == "6_stairs", self.genome))) > 5:
            penalties -= 2
        # STUDENT If you go for the FI-2POP extra credit, you can put constraint calculation in here too and cache it in a new entry in __slots__.
        self._fitness = sum(map(lambda m: coefficients[m] * measurements[m],
                                coefficients)) + penalties
        return self

    def fitness(self):
        if self._fitness is None:
            self.calculate_fitness()
        return self._fitness

    def mutate(self, genome):
        mutation_rate = 0.05

        for x in range(2, width-2):

            if random.random() < mutation_rate:

                # clear this column
                for y in range(1,14):
                    genome[y][x] = "-"

                choice = random.random()


                # platform / blocks
                if choice < 0.35:

                    height_block = random.randint(1,3)

                    for h in range(height_block):
                        genome[13-h][x] = random.choice([
                            "X",
                            "B",
                            "?"
                        ])


                # coins above ground
                elif choice < 0.55:

                    y = random.randint(7,11)
                    genome[y][x] = "o"


                # enemy only on ground
                elif choice < 0.75:

                    genome[14][x] = "E"


                # pipe
                else:

                    pipe_height = random.randint(2,4)

                    genome[15-pipe_height][x] = "T"

                    for y in range(16-pipe_height,15):
                        genome[y][x] = "|"


        return genome

    # Apply the DEs to a base level.
    def to_level(self):
        if self._level is None:
            base = Individual_Grid.empty_individual().to_level()
            for de in sorted(self.genome, key=lambda de: (de[1], de[0], de)):
                # de: x, type, ...
                x = de[0]
                de_type = de[1]
                if de_type == "4_block":
                    y = de[2]
                    breakable = de[3]
                    base[y][x] = "B" if breakable else "X"
                elif de_type == "5_qblock":
                    y = de[2]
                    has_powerup = de[3]  # boolean
                    base[y][x] = "M" if has_powerup else "?"
                elif de_type == "3_coin":
                    y = de[2]
                    base[y][x] = "o"
                elif de_type == "7_pipe":
                    h = de[2]
                    base[height - h - 1][x] = "T"
                    for y in range(height - h, height):
                        base[y][x] = "|"
                elif de_type == "0_hole":
                    w = de[2]
                    for x2 in range(w):
                        base[height - 1][clip(1, x + x2, width - 2)] = "-"
                elif de_type == "6_stairs":
                    h = de[2]
                    dx = de[3]  # -1 or 1
                    for x2 in range(1, h + 1):
                        for y in range(x2 if dx == 1 else h - x2):
                            base[clip(0, height - y - 1, height - 1)][clip(1, x + x2, width - 2)] = "X"
                elif de_type == "1_platform":
                    w = de[2]
                    h = de[3]
                    madeof = de[4]  # from "?", "X", "B"
                    for x2 in range(w):
                        base[clip(0, height - h - 1, height - 1)][clip(1, x + x2, width - 2)] = madeof
                elif de_type == "2_enemy":
                    base[height - 2][x] = "E"
            self._level = base
        return self._level

    @classmethod
    def empty_individual(_cls):
        # STUDENT Maybe enhance this
        g = []
        return Individual_DE(g)

    @classmethod
    def random_individual(cls):
        # STUDENT consider putting more constraints on this to prevent pipes in the air
        # STUDENT also consider weighting the different tile types so it's not uniformly random

        g = [["-" for col in range(width)] for row in range(height)]

        # floor
        g[15][:] = ["X"] * width

        # mario start
        g[14][0] = "m"

        # goal
        g[7][-1] = "v"
        for row in range(8,14):
            g[row][-1] = "f"

        # Generate structures instead of random noise
        for x in range(5, width - 5):

            chance = random.random()

            # platforms
            if chance < 0.08:
                y = random.randint(8,12)
                length = random.randint(3,8)

                for i in range(length):
                    if x+i < width-1:
                        g[y][x+i] = "X"


            # blocks
            elif chance < 0.12:
                y = random.randint(8,12)
                g[y][x] = random.choice(["X","B","?"])


            # coins
            elif chance < 0.18:
                y = random.randint(6,10)
                g[y][x] = "o"


            # enemies
            elif chance < 0.22:
                g[14][x] = "E"


            # pipes
            elif chance < 0.25:
                height_pipe = random.randint(2,5)

                g[15-height_pipe][x] = "T"

                for y in range(16-height_pipe,15):
                    g[y][x] = "|"


        g[14:16][-1] = ["X","X"]

        return cls(g)


Individual = Individual_Grid

def generate_successors(population):
    results = []

    """
    Selection Strat #1: Elitist
    always carry best individual to next gen unchanged
    Guarantees fitness never regresses due to tournament loss or unlucky mutation
    """
    elite_count = max(1, int(0.02 * len(population)))
    elites = heapq.nlargest(elite_count, population, key=Individual.fitness)
    results.extend(elites)

    """
    Selection Strat #2: Tournament
    sample small, random subset of population and fittest member = parent
    Balance explore v exploit: small tournament allows weaker individuals
    to occasionally pass through, still biasing fitness
    """
    tournament_size = 5

    while len(results) < len(population):

        # Select parent 1
        candidates = random.sample(population, tournament_size)
        parent1 = max(candidates, key=Individual.fitness)

        # Select parent 2
        candidates = random.sample(population, tournament_size)
        parent2 = max(candidates, key=Individual.fitness)

        # Crossover + mutation
        children = parent1.generate_children(parent2)

        results.extend(children)

    return results[:len(population)]

def ga():
    # STUDENT Feel free to play with this parameter
    pop_limit = 480
    # Code to parallelize some computations
    batches = os.cpu_count()
    if pop_limit % batches != 0:
        print("It's ideal if pop_limit divides evenly into " + str(batches) + " batches.")
    batch_size = int(math.ceil(pop_limit / batches))
    with mpool.Pool(processes=os.cpu_count()) as pool:
        init_time = time.time()
        # STUDENT (Optional) change population initialization
        population = [Individual.random_individual() if random.random() < 0.9
                      else Individual.empty_individual()
                      for _g in range(pop_limit)]
        # But leave this line alone; we have to reassign to population because we get a new population that has more cached stuff in it.
        population = pool.map(Individual.calculate_fitness,
                              population,
                              batch_size)
        init_done = time.time()
        print("Created and calculated initial population statistics in:", init_done - init_time, "seconds")
        generation = 0
        start = time.time()
        now = start
        print("Use ctrl-c to terminate this loop manually.")
        try:
            while True:
                now = time.time()
                # Print out statistics
                if generation > 0:
                    best = max(population, key=Individual.fitness)
                    print("Generation:", str(generation))
                    print("Max fitness:", str(best.fitness()))
                    print("Average generation time:", (now - start) / generation)
                    print("Net time:", now - start)
                    with open("levels/last.txt", 'w') as f:
                        for row in best.to_level():
                            f.write("".join(row) + "\n")
                generation += 1
                # STUDENT Determine stopping condition
                stop_condition = False
                if stop_condition:
                    break
                # STUDENT Also consider using FI-2POP as in the Sorenson & Pasquier paper
                gentime = time.time()
                next_population = generate_successors(population)
                gendone = time.time()
                print("Generated successors in:", gendone - gentime, "seconds")
                # Calculate fitness in batches in parallel
                next_population = pool.map(Individual.calculate_fitness,
                                           next_population,
                                           batch_size)
                popdone = time.time()
                print("Calculated fitnesses in:", popdone - gendone, "seconds")
                population = next_population
        except KeyboardInterrupt:
            pass
    return population


if __name__ == "__main__":
    final_gen = sorted(ga(), key=Individual.fitness, reverse=True)
    best = final_gen[0]
    print("Best fitness: " + str(best.fitness()))
    now = time.strftime("%m_%d_%H_%M_%S")
    # STUDENT You can change this if you want to blast out the whole generation, or ten random samples, or...
    for k in range(0, 10):
        with open("levels/" + now + "_" + str(k) + ".txt", 'w') as f:
            for row in final_gen[k].to_level():
                f.write("".join(row) + "\n")
