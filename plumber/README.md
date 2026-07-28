# Plumber

Plumber is an interpreted, concurrent extension of Blang for prototyping
multi-room protocols before assigning 2D geometry.

```text
program pipeline

pipe queue 16..

block main {
  forever {
    A = recv input
    send worker
  }
}

block worker {
  forever {
    A = recv main
    B = A
    A += B
    send output
  }
}
```

Every block is a persistent actor with private signed 64-bit registers `A` and
`B`. All blocks start together, with `main` scheduled first when it exists.
One block may receive from the predefined `input` endpoint, and any block may
send to the predefined `output` endpoint. A `main` block is optional.

`send worker` writes `A` to the directed channel from the current block to
`worker`. `A = recv worker` reads from the channel in the opposite direction.
Channels are independent bounded FIFOs. A send to a full channel and a receive
from an empty channel block only the executing actor.

Top-level named pipes are persistent FIFOs that are not owned by an actor:

```text
pipe storage 17..
```

Any block may use `send storage` and `A = recv storage`. The declared minimum
is the pipe's capacity in the interpreter and its required physical capacity
when compiling to `.man`. The current `.man` compiler requires one sending
block and one receiving block per named pipe. They may be the same block; in
that case Plumber inserts a small relay room because physical pipes cannot
return directly to their source room.

Pipe sizes use `MIN..MAX` ranges. Either bound, or the complete range, may be
omitted:

```text
pipe exact_window 17..32
pipe at_least_17 17..
pipe at_most_32 ..32
pipe unconstrained
```

The interpreter uses deterministic round-robin scheduling and executes at most
one machine instruction per runnable block in each scheduler round.

## Statements

```text
A = INTEGER
B = A
swap

A += B
A -= B
A *= B
A %= B
A /= B
A = -A
A &= B
A |= B
A ^= B
A <<= B
A >>= B

A = recv BLOCK
send BLOCK
halt
nop
```

Structured control supports nested loops:

```text
repeat A {
  ...
}

while positive A {
  ...
}

if sign A {
  negative { ... }
  zero { ... }
  positive { ... }
}
```

`repeat A` snapshots `max(A, 0)` when the loop is entered. Loop counts are
interpreter state, so nested loops are allowed.

`while positive A` tests `A` before entry and after every iteration. It is
useful for sentinel-terminated streams whose payload values are positive.

## Run

From the `plumber` directory:

```sh
go run . \
  -program examples/pipeline.plumb \
  -input "1 -3 42"
```

Useful flags:

```text
-man OUTPUT.man
-floorplan-mode shelf|anneal
-channel-capacity 1
-max-steps 1000000
-actors
```

`-man` compiles every Plumber actor through Blang, places the generated
rooms on a spacious floor, routes peer channels with the existing floorplanner,
and validates that the resulting Little Man program parses.

The default `shelf` floorplanner performs deterministic fixed-outline searches.
The separate `anneal` mode uses deterministic multi-start simulated annealing
to move rooms and I/O ports inside progressively smaller square outlines. It
scores overlap, clearance, cross-room literal conflicts, connectivity, and
estimated wire length before passing its best candidates to the real router:

```sh
go run . \
  -program examples/bubble_sort.plumb \
  -floorplan-mode anneal \
  -man /tmp/sort_bubble_plumber.man
```

Normal persistent programs finish in `waiting-input` after consuming the
provided input. `deadlocked` means no block can execute and `main` is not
waiting for external input.

The `examples/sort_chain3.plumb` program is a three-cell version of the
streaming comparator sorter.

The smaller `examples/bubble_sort.plumb` program stores positive encoded values
and a zero boundary in a named 17-cell pipe, performs 15 complete bubble passes,
then drains the sorted values:

```sh
go run . \
  -program examples/bubble_sort.plumb \
  -input "5 7 2 9 -3 1"
```
