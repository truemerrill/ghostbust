# ghostbust

[![PyPI - Version](https://img.shields.io/pypi/v/ghostbust.svg)](https://pypi.org/project/ghostbust)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ghostbust.svg)](https://pypi.org/project/ghostbust)

-----

Ghostbust is a runtime code analysis tool designed to identify and flag dead or orphaned functions within your codebase. The tool leverages cProfile to profile code execution and stores the profiles in a local cache. Moreover, Ghostbust scrutinizes the functions declared in your source code, providing comprehensive insights into code health and highlighting areas that may benefit from optimization or refactoring.

## Usage

```console
Usage: ghostbust [OPTIONS] COMMAND [ARGS]...

  Runtime code analysis of orphaned (dead code) functions.

Options:
  --help  Show this message and exit.

Commands:
  cache    List scripts currently in the profiler cache.
  clear    Clear the profiler cache.
  inspect  List functions declared within code sources.
  orphans  List declared functions which are never used.
  profile  Profile a Python script and add to the cache.
  stats    List the profiler stats for a cached script run.
```

### Profile a script

First, lets create an example program to analyze.  The following script declares
two functions but only one is ever used.

```console
cat <<EOF > script.py
from math import sin

def called(x):
    return sin(x)

def never_called(x):
    return x

called(0)
EOF
```

To discover orphaned functions, we first have to do a runtime analysis by executing
the program with `cProfile` profiling.

```console
ghostbust profile script.py --numlines 3
Fri Nov 17 12:02:32 2023    /Users/jmerrill3/Repositories/ghostbust/.ghostbust/prof/b83794c1de1e00452661a5530443cd2f72eccca40f104496fd323e8fed308e6e.prof

         0 function calls in 0.000 seconds

   Ordered by: cumulative time
   List reduced from 72 to 3 due to restriction <3>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.001    0.001 {built-in method builtins.exec}
        1    0.000    0.000    0.001    0.001 script.py:1(<module>)
        1    0.000    0.000    0.001    0.001 <frozen importlib._bootstrap>:1167(_find_and_load)
```

## List orphaned functions

```console
ghostbust orphans script.py 
  never_called                 script.py:6
```

## Installation

```console
pip install ghostbust
```

## License

`ghostbust` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
