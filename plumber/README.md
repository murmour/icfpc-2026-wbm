# Plumber

Plumber is a concurrent extension of [Blang](../blang) for building multi-room `.man` programs.

It has both a source-level interpreter and a compiler to `.man` files through [Blang](../blang) and [Floorplan](../floorplan).

Features:
- Concurrent actors with private registers and blocking FIFO channels.
- Structured programming constructs (arithmetic, branches, loops).
- A source-level interpreter for debugging.
- A compiler to `.man` files through [Blang](../blang) and [Floorplan](../floorplan).


## Example: Motion Energy

```text
program motion_energy

block delta {
  forever {
    A = recv input
    swap
    A = -A
    A += B
    send square
  }
}

block square {
  forever {
    A = recv delta
    B = A
    A *= B
    send output
  }
}
```

It's a streaming motion-energy detector:
- `delta` retains the previous sample in `B` and emits  `current - previous`.
- `square` receives each difference and emits its square.

Corresponding  `.man` output:
```text
 >--v   >--v   >--v
 ^  v   ^  v   ^  v
+-++-----++-----++-+
|I||>@rWv||>@rMv||O|
+-+|^s+N<||^ s*<|+-+
   +-----++-----+
```


## Example: Pipeline

```text
program pipeline

pipe queue 16..

block main {
  forever {
    A = recv input
    send queue
  }
}

block worker {
  forever {
    A = recv queue
    B = A
    A += B
    send output
  }
}
```

The named pipe buffers at least 16 values, allowing the input actor to keep accepting work while the doubling actor is temporarily behind.


## Basics

Every block is a persistent actor with private signed 64-bit registers `A` and `B`. All blocks start together, with `main` scheduled first when it exists. One block may receive from the predefined `input` endpoint, and any block may send to the predefined `output` endpoint.

`send worker` writes `A` to the directed channel from the current block to `worker`. `A = recv worker` reads from the channel in the opposite direction. Channels are independent bounded FIFOs. A send to a full channel and a receive from an empty channel block only the executing actor.

Top-level named pipes are persistent FIFOs that are not owned by an actor:
```text
pipe storage 17..
```

Any block may use `send storage` and `A = recv storage`. The declared minimum is the pipe's capacity in the interpreter and its required physical capacity when compiling to `.man`. The current `.man` compiler requires one sending block and one receiving block per named pipe. They may be the same block; in that case Plumber inserts a repeater.

Pipe sizes use `MIN..MAX` ranges. Either bound, or the complete range, may be omitted:

```text
pipe exact_window 17..32
pipe at_least_17 17..
pipe at_most_32 ..32
pipe unconstrained
```


## Statements

Same as in [Blang](../blang), except that nested loops are allowed.


## Floorplanning

The default `shelf` floorplanner performs deterministic fixed-outline searches. The separate `anneal` mode uses deterministic multi-start simulated annealing to move rooms and I/O ports inside progressively smaller square outlines. It scores overlap, clearance, cross-room literal conflicts, connectivity, and estimated wire length before passing its best candidates to [Floorplan](../floorplan).


## Algorithm

Plumber operates at two levels.

At the source level, it parses blocks into an actor graph and validates every directed channel. Each actor has private, persistent `A` and `B` registers. The interpreter schedules actors round-robin, one instruction at a time. Receiving from an empty pipe or sending to a full pipe blocks only that actor, providing synchronization and backpressure without explicit scheduling code.

For physical compilation, Plumber:

1. Lowers named storage pipes into tiny relay actors.
2. Infers the input and output ports of every actor.
3. Translates each actor into an independent Blang program.
4. Invokes Blang to generate one `.block` room per actor.
5. Searches for increasingly compact room placements.
6. Uses Floorplan to route the channels between rooms.
7. Rejects layouts with overlaps, quote conflicts, routing failures, or invalid generated `.man` code.

The optional annealing mode uses topology-aware initial placements and simulated annealing before asking the real router to connect the best candidates.


## Relationship to Blang

The toolchain is:
```text
Plumber actors -> Blang programs -> .block rooms -> Floorplan -> .man
```

Blang handles structured control flow inside one room. Plumber handles protocols between rooms.

The languages deliberately share the same `A`/`B` operations and control-flow syntax. Plumber adds persistent actors, directed bounded FIFOs, blocking, named storage pipes, and a source-level interpreter. During physical compilation, each ordinary Plumber actor becomes a generated Blang source file.
