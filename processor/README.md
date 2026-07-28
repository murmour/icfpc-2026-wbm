# Processor

This directory contains a small general-purpose CPU implemented in Little Man and an assembler implemented in Rust that turns assembly programs into complete `.man` solutions. The generated floor includes the program source, the required register bank, the CPU, optional memory, and an optional display.

The assembler determines the number of registers from the largest referenced register. It omits memory when the program has no `load` or `store` instructions and omits the display unless the source declares `.screen`.

Run commands from this directory because the assembler loads the adjacent `.mod` templates.


## Build

Install Rust and run:
```sh
make
```

## Usage

Assemble a program:

```sh
./assembler path/to/program.asm output.man
```

This writes:

- `output.man`, the complete Little Man program;
- `output_program_room.txt`, the generated cyclic program-source room.

Use a two-lane register bank instead of the default single-lane bank with:

```sh
./assembler PATH/TO/program.asm output.man --two-lane-registers
```

The two-lane bank rounds an odd register count up to an even number of physical cells.

Add `--test` to run the applicable built-in reference tests after assembly:

```sh
./assembler PATH/TO/program.asm output.man --test
```

Test data is embedded at assembler build time from `../public_tests`.


## Source Format

Assembly is case-insensitive. Commas are optional. Both `;` and `#` start a comment. Registers may be written as `r0`, `r1`, and so on. A label is an identifier followed by `:`.

```asm
start:
  read r2
  imm r3, 1
  add r4, r2, r3
  write r4
  jmp start
```

Jumps use labels. The assembler converts each label into a forward word skip through the cyclic program stream, including wraparound for backward jumps.


### Directives

```asm
.memory 64
.memory 64 160
.screen 16 16
.kind snake
```

- `.memory SIZE [PIPE_CELLS]` configures RAM. The storage pipe defaults to `2 * SIZE`; an explicit size must be even and at least `2 * SIZE`. The memory module is generated only when the program accesses memory. A program that accesses memory without this directive receives 8 slots and a 16-cell storage pipe.
- `.screen WIDTH HEIGHT` adds a display of a specified size (from 1 through 64).
- `.kind NAME` selects reference tests for `snake`, `pathfinder`, `lllm`, `llm`, or `matmul`.

Repeated source can be generated with an inclusive range. `{i}` is replaced with the current index:

```asm
.repeat 2 5
  imm r{i} 0
.endrepeat
```


## Instructions

### Data Movement

```asm
mov   DST SRC
imm   DST VALUE
read  DST
write SRC
load  DST ADDRESS
store ADDRESS SRC
```

`load` and `store` are register-indirect:

```text
DST = memory[register[ADDRESS]]
memory[register[ADDRESS]] = register[SRC]
```

`write` is unavailable in screen programs because that opcode is used by the display protocol.


### Arithmetic

Three-address register operations:

```asm
add DST LHS RHS
sub DST LHS RHS
mul DST LHS RHS
div DST LHS RHS
and DST LHS RHS
shr DST LHS RHS
```

Immediate forms:

```asm
addi DST LHS VALUE
subi DST LHS VALUE
muli DST LHS VALUE
divi DST LHS VALUE
```

The physical ALU accumulates into `r0`. Accumulator instructions expose that fast path directly:

```asm
add0 r7
sub0 r7
mul0 r7
div0 r7
and0 r7
shr0 r7
xor0 r7

addi0 16
subi0 16
muli0 16
divi0 16
andi0 16
shri0 16
xori0 16
```

For example, `add0 r7` computes `r0 = r0 + r7`, while `addi0 16` computes `r0 = r0 + 16`.

Additional pseudo-instructions:

```asm
inc REG
dec REG
neg REG
alu OP
```

`alu OP` applies the named operation to `r0` and `r1`. Valid names are `add`, `mul`, `sub`, `div`, `and`, `shr`, and `xor`; their Little Man symbols are accepted as aliases.

Division follows Little Man semantics: the quotient is floored and the remainder is left in the secondary ALU register. Division by zero produces a zero quotient and preserves the dividend as the remainder.


### Control Flow

```asm
jc   COND LABEL
jpos COND LABEL
jmp  LABEL

jeq   REG VALUE LABEL
jeqs  REG VALUE LABEL
jeqr  LHS RHS LABEL
jeqrs LHS RHS LABEL
```

`jc` and `jpos` jump only when `register[COND] > 0`. The equality operations are assembler pseudo-instructions; the `s` variants use a shorter comparison sequence when its constraints are suitable.


### Display

A source containing `.screen` uses:

```asm
screen_addr REG
screen_data REG
screen_swap REG
```

`screen_commit` is an alias for `screen_swap`.

- `screen_addr` selects the pixel address.
- `screen_data` writes a palette index to the back buffer.
- `screen_swap` presents the frame. Its register value controls whether the previous frame is preserved according to the display protocol.


### Packed Loads

The assembler includes specialized packed-memory helpers:

```asm
load4 DST POSITION ADDRESS INDEX FACTOR QUOTIENT
load8 DST POSITION ADDRESS INDEX FACTOR QUOTIENT
```

They extract a 4-bit or 8-bit value from packed memory while using the named registers as working storage.

`matmul` emits the specialized Matrix Multiplication routine used by the corresponding task source.


## Machine Model

The program source continuously streams instruction words through a ring. The CPU consumes one opcode followed by that instruction's operands. Branches discard a computed number of words from the same cyclic stream.

The register and memory peripherals share a request protocol:

```text
INDEX 0
    Read slot INDEX and return its value.

INDEX 1 VALUE
    Replace slot INDEX with VALUE.
```

Register operands are literal indices. Memory addresses are obtained by reading the specified address register first.


### Word Encoding

Without a display:

| Opcode | Instruction | Words |
|---:|---|---|
| 0 | `mov DST SRC` | `0 DST SRC` |
| 1 | `store ADDRESS SRC` | `1 ADDRESS SRC` |
| 2 | `load DST ADDRESS` | `2 DST ADDRESS` |
| 3 | `imm DST VALUE` | `3 VALUE DST` |
| 4 | `read DST` | `4 DST` |
| 5 | `write SRC` | `5 SRC` |
| 6 | ALU | `6 OP SRC` |
| 7 | positive jump | `7 OFFSET COND` |
| 8 | unconditional jump | `8 OFFSET` |

With a display, opcodes 0 through 4 are unchanged. Opcodes 5, 6, and 7 become `screen_swap`, `screen_addr`, and `screen_data`; ALU, positive jump, and unconditional jump move to opcodes 8, 9, and 10.

ALU operation numbers are:

| Operation | Code |
|---|---:|
| add | 0 |
| multiply | 1 |
| subtract | 2 |
| divide | 3 |
| bitwise AND | 4 |
| shift right | 5 |
| bitwise XOR | 6 |

Offsets are forward word counts measured after the jump instruction has consumed its own words. Assembly authors normally use labels and do not need to calculate them.


## Floorplanning

The floor is assembled from:

- `meta_template.mod`, the universal component layout;
- `cpu.mod`, the ordinary CPU;
- `cpu_screen.mod`, the display-capable CPU;
- `memory.mod`, the optional memory bank.

Register cells are repeaters initialized to zero. The assembler places only as many cells as the highest referenced register requires. RAM uses a generated accordion storage pipe sized by `.memory`. The program source is packed into the smallest feasible horizontal or vertical room and connected to the CPU by a buffered cyclic pipe.
