# Blang

Blang is a small structured language that compiles one-man programs into the
JSON `.block` format consumed by the block tester and `floorplan`. It exposes the
little man's `A` and `B` registers while reserving the backpack for generated
loop control.

Compile a source file:

```sh
cd blang
go run . \
  -input examples/ring34_exchange.bl \
  -output /tmp/ring34_exchange.block
cd ../sim
go run tester.go parser.go simulator.go types.go literals.go \
  /tmp/ring34_exchange.block
```

## Structure

```text
block example

input request auto
input data top 4 2 64
output response auto 2 128

forever {
  A = recv request
  send response
}

test smoke {
  input request: 42
  expected response: 42
  loopback response: request
}
```

A port is declared as one of:

```text
input NAME auto [MIN_LENGTH MAX_LENGTH]
output NAME auto [MIN_LENGTH MAX_LENGTH]
input NAME SIDE OFFSET MIN_LENGTH MAX_LENGTH
output NAME SIDE OFFSET MIN_LENGTH MAX_LENGTH
```

`SIDE` is `top`, `bottom`, `left`, or `right`. Automatic placement assigns
distinct wall positions and verifies every named send and receive against the
machine's Manhattan-distance and reading-order rules.

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

A = recv PORT
A = recv any
send PORT
broadcast
halt
nop
```

For compact generated code, `raw CODE` inserts a validated sequence of
arithmetic machine instructions directly:

```text
raw 7M*
```

`A = recv any` emits `R` and receives from whichever declared input has a value
ready. `broadcast` emits `S` and atomically sends `A` to every declared output.

Loops use the backpack internally:

```text
repeat A {
  # Runs max(A, 0) times.
}
```

Sign control has three eastbound branches:

```text
if sign A {
  negative {
    A = -1
  }
  zero {
    A = 0
  }
  positive {
    A = 1
  }
}
```

The top-level `forever` block is required and becomes the room's persistent
control loop. Nested `repeat` statements are rejected because one backpack
cannot hold two active counters. Statements inside a sign branch may contain a
repeat, and sign branches may be nested.

The compiler prioritizes readable source and correct geometry. Its generated
control flow is intentionally regular and is not yet a size optimizer.
