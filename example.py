from math import floor, cos as c

import numpy as np
import time
from numpy.random import poisson


def my_function(x):
    time.sleep(3)
    y = x + 1 + np.random.normal()
    return np.sin(x) + c(y)


def never_called(y):
    print(y)


my_function(10)
