"""
The MIT License (MIT)
Copyright (C) 2023 True Merrill <true.merrill@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import ast
import json
import os
import pstats
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import List, Set, Tuple

import click

__version__ = "0.1.0"

GHOSTBUST_DIR = os.getenv("GHOSTBUST_DIR", str(Path.cwd() / ".ghostbust"))


def _relative_to_cwd(path: Path) -> str:
    try:
        filename = str(path.relative_to(Path.cwd()))
    except ValueError:
        filename = str(path)
    return filename


def _profile_file_hash(file: Path) -> str:
    return sha256(str(file.absolute()).encode()).hexdigest()


def _profile_file_path(file: Path) -> Path:
    hsh = _profile_file_hash(file)
    return Path(GHOSTBUST_DIR) / "prof" / f"{hsh}.prof"


def _profile_cache_file_path() -> Path:
    return Path(GHOSTBUST_DIR) / "cache.json"


def _read_profile_cache() -> dict[str, str]:
    try:
        with open(_profile_cache_file_path()) as io:
            cache = json.load(io)
    except FileNotFoundError:
        cache = {}
    return cache


def _write_profile_cache(cache: dict[str, str]):
    with open(_profile_cache_file_path(), "w") as io:
        json.dump(cache, io, indent=2, sort_keys=True)


def _profile(file: Path) -> Path:
    """Profile a script.

    Note: This executes the script using the cProfile profiler and caches the
    profile into a local file.  The cache file is deterministic and uniquely
    depends on the path to the script file (including the script filename).
    This function will overwrite a prior cache file if it exists.

    Args:
        file (Path): the script to profile

    Returns:
        Path: the cache file storing the profile results
    """
    cache = _read_profile_cache()
    profile_file = _profile_file_path(file)
    profile_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [  # noqa: S603
            sys.executable,
            "-m",
            "cProfile",
            "-o",
            str(profile_file),
            str(file),
        ],
        check=False,
    )
    cache[str(file.absolute())] = str(profile_file)
    _write_profile_cache(cache)
    return profile_file


def _clear_cache():
    """Clear the profile cache."""
    for file in (Path(GHOSTBUST_DIR) / "prof").glob("*.prof"):
        file.unlink()
    _write_profile_cache({})


FuncRef = Tuple[str, int, str]


def _stats_from_profile_file(
    profile_file: Path, sort_by: str = "tottime", numlines=25
) -> str:
    stats = pstats.Stats()
    stats.load_stats(str(profile_file))
    with StringIO() as output:
        with redirect_stdout(output):
            stats.strip_dirs().sort_stats(sort_by).print_stats(numlines)
        result = output.getvalue()
    return result


def _called_funcs_from_profile_file(profile_file: Path) -> Set[FuncRef]:
    def abspath(path: str):
        return str(Path(path).absolute())

    stats = pstats.Stats()
    stats.load_stats(str(profile_file))
    return {(abspath(f), line, fn) for f, line, fn in stats.stats.keys()}


def _called_funcs() -> Set[FuncRef]:
    """Get the set of functions called in all cached profile runs.

    Returns:
        Set[FuncRef]: The set of references of called functions.
    """
    funcs = set()
    prof_dir = Path(GHOSTBUST_DIR) / "prof"
    for profile_file in prof_dir.glob("*.prof"):
        funcs.update(_called_funcs_from_profile_file(profile_file))
    return funcs


class DeclaredFuncVisitor(ast.NodeVisitor):
    """AST visitor to log functions declared in a source file."""

    def __init__(self, filename: Path):
        self.filename = str(filename.absolute())
        self.funcs = []

    def visit_FunctionDef(self, node):  # noqa: N802
        func_ref = (self.filename, node.lineno, node.name)
        self.funcs.append(func_ref)


def _declared_funcs_from_source_file(source_file: Path) -> Set[FuncRef]:
    with open(source_file) as io:
        source = ast.parse(io.read(), filename=str(source_file))

    funcs = []
    for node in ast.walk(source):
        visitor = DeclaredFuncVisitor(source_file)
        visitor.visit(node)
        funcs.extend(visitor.funcs)
    return set(funcs)


def _declared_funcs(pattern: Tuple[str, ...]) -> Set[FuncRef]:
    """Get the set of functions declared in a series of files.

    Args:
        glob (str): the glob pattern specifying the files to
            inspect for functions.

    Returns:
        Set[FuncRef]: The set of references of declared functions.
    """
    funcs: Set[FuncRef] = set()
    for glob in pattern:
        for source_file in Path.cwd().glob(glob):
            funcs.update(_declared_funcs_from_source_file(source_file))
    return funcs


TableRow = Tuple[str, str]


def _table_row(func_ref: FuncRef, colwidth=28) -> TableRow:
    def _function_name(fn: str):
        if len(fn) > colwidth:
            return f"{fn[:(colwidth - 3)]}..."
        return fn

    def _source_location(filename, lineno):
        return f"{_relative_to_cwd(Path(filename))}:{lineno}"

    filename, lineno, fn = func_ref
    return _function_name(fn), _source_location(filename, lineno)


def _table_rows(funcs: Set[FuncRef], colwidth=28) -> List[TableRow]:
    return [_table_row(f, colwidth) for f in sorted(funcs)]


def _table_line(row: TableRow, indent=2, colwidth=28) -> str:
    name, location = row
    return f"{' ' * indent}{name:<{colwidth}} {location}"


@contextmanager
def spinner(message: str):
    """A context manager to display a spinner on stdout."""
    spinner_chars = ["-", "\\", "|", "/"]
    stop_spinner = threading.Event()

    def spin():
        while getattr(threading.current_thread(), "running", True):
            for char in spinner_chars:
                if stop_spinner.is_set():
                    return None
                print(f"\r{message} {char}", end="", flush=True)  # noqa: T201
                time.sleep(0.1)

    spinner_thread = threading.Thread(target=spin, daemon=True)
    spinner_thread.start()

    try:
        yield
    finally:
        stop_spinner.set()
        spinner_thread.join()
        print("\r", end="", flush=True)  # noqa: T201


@click.group()
def cli():
    """Runtime code analysis of orphaned (dead code) functions."""
    pass


@cli.command()
@click.argument("script", required=True)
@click.option("-n", "--numlines", default=25, type=int)
@click.option(
    "-s",
    "--sortby",
    default="cumtime",
    type=click.Choice(
        ["ncals", "tottime", "percall", "cumtime", "filename"],
        case_sensitive=False,
    ),
)
def profile(script, numlines, sortby):
    """Profile a Python script and add to the cache."""
    with spinner(f"Profiling {script}"):
        prof_file = _profile(Path(script))
    stats = _stats_from_profile_file(
        prof_file, sort_by=sortby, numlines=numlines
    )
    click.echo(stats)


@cli.command()
@click.argument("script", required=True)
@click.option("-n", "--numlines", default=25, type=int)
@click.option(
    "-s",
    "--sortby",
    default="cumtime",
    type=click.Choice(
        ["ncals", "tottime", "percall", "cumtime", "filename"],
        case_sensitive=False,
    ),
)
def stats(script, numlines, sortby):
    """List the profiler stats for a cached script run."""
    try:
        prof_file = _profile_file_path(Path(script))
        stats = _stats_from_profile_file(
            prof_file, sort_by=sortby, numlines=numlines
        )
        click.echo(stats)
    except FileNotFoundError:
        click.echo(
            f'No cache entry for "{script}".  Use "ghostbust profile" first.'
        )


@cli.command()
def cache():
    """List scripts currently in the profiler cache."""
    profile_cache = _read_profile_cache()
    for filename in profile_cache.keys():
        click.echo(f"  {_relative_to_cwd(Path(filename))}")


@cli.command()
def clear():
    """Clear the profiler cache."""
    _clear_cache()


@cli.command()
@click.argument("pattern", required=True, nargs=-1)
def inspect(pattern):
    """List functions declared within code sources."""
    funcs = _declared_funcs(pattern)
    for row in _table_rows(funcs):
        click.echo(_table_line(row))


@cli.command()
@click.argument("pattern", required=True, nargs=-1)
def orphans(pattern):
    """List declared functions which are never used."""
    cache = _read_profile_cache()
    if len(cache) == 0:
        click.echo(
            'Profiler cache is currently empty. Use "ghostbust profile" first.'
        )
    else:
        declared_funcs = _declared_funcs(pattern)
        called_funcs = _called_funcs()
        orphan_funcs = declared_funcs - called_funcs
        for row in _table_rows(orphan_funcs):
            click.echo(_table_line(row))


if __name__ == "__main__":
    cli()
