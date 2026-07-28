# Simulacrum

This piece of code is a **truly-high-speed** interpreter for Little Man programs.

Want to build it? Run `make`.

Want to use it? See built-in help in `./simulacrum`.

Want to test it? Run `make benchmark`.

Want to _feel_ it? See `TV_MODE` below.


## How it works

Traced JIT compilation with an event-driven execution model.

At load time, Simulacrum finds rooms, literals, displays, and complete pipe paths. It then:

1. Traces every reachable `(cell, entrance direction)` state.
2. Converts relative two-dimensional movements into direct trace targets.
3. Interns literals and branch targets into compact tables.
4. Collapses empty-path operations while preserving their tick cost.
5. Schedules runnable men, pipe arrivals, and pipe-source releases by tick.
6. Wakes blocked men only when their read or write can make progress.

The result -- **speed**.

Gotcha: doesn't support `Y`.


## Profiler

Enabled by the `PROFILE_MODE` conditional define.

When run with `--profile`, produces a report:

- Active, waiting, and blocked ticks for every man.
- Counts of sends, reads, loads, ALU operations, branches, and skipped cells.
- Waiting time attributed to individual man/pipe pairs.
- Pipe lengths, send and consume counts, and total backpressure.


## TV Mode

Enabled by the `TV_MODE` conditional define. Needs SDL.

When run with `--display`, emulates an LM-75 display in real-time.

Use like this: `./simulacrum ../demon/metaballs.man --display`.
