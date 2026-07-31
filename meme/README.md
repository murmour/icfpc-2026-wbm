# Meme

Meme is an imperative language with built-in indexed memory.

It compiles complete programs into `.man` files directly.

Features:
- Fixed and dynamic memory declarations.
- Indexed loads and stores.
- Integer and bitwise expressions.
- Input, output, assignments, loops, and branches.
- Dynamic-array operations such as `push` and `extract_min`.
- Collision-checked generation of rooms, pipes, and control paths.

100% vibe-coded by a crazy graph theorist.

Meme has backends that are specialized for specific problems (as selectable profiles):
- Memory
- Sudoku Auditor
- Sort
- Packet Reassembly
- Grade Book

For examples, see Case Studies below.


## Language

Every file starts with a program name, followed by optional memory declarations:

```text
program NAME
memory cells[100] = 0
dynamic memory values[16]
```

A fixed `memory` starts with the given value in every slot.

A `dynamic memory` declares a maximum capacity but starts empty.

Expressions contain integers, variables, indexed values, parentheses, and these binary operators:
```text
+  -  *  /  %  &  |  ^  <<  >>
```

The supported control and I/O statements are:
```text
x = input()
output(expression)
x = expression
x = cells[index]
cells[index] = expression
cells[index] = input()

repeat count:
    ...

if value == 0:
    ...
else:
    ...

forever:
    ...
```

Blocks use indentation.

`repeat` takes a variable as its count.

`if` tests a variable against zero and requires an `else` branch.

Comments start with `#`.

Dynamic arrays support:
```text
values.push(input())
minimum = values.extract_min()
```

Indices have to be variables. An indexed load must also be assigned to a variable before it is used inside a larger expression:
```text
value = cells[index]
result = value + 1
```

The `gradebook(...)` and `packet_reassembly(...)` statements invoke operations implemented by their corresponding problem-specific placers.


## Architecture

The compilation pipeline is:
```text
Meme source -> IR -> profile-based floorplanner -> .man
```

The floorplanning stage generates a complete physical layout directly. It creates the main room, storage rings, relay rooms, I/O rooms, and connecting pipes.

Memories are generally represented by token rings. Indexed operations rotate a ring to the requested element, access it, and restore the known logical head. Storage pipes are folded into compact accordions, and generated geometry is checked for collisions on placement.


## Case study: Memory

Self-descriptive:
```text
program Memory

memory cells[100] = 0

forever:
    op = input()
    address = input()
    if op == 0:
        output(cells[address])
    else:
        cells[address] = input()
```


## Case study: Sort

Self-descriptive:
```text
program Sort

dynamic memory values[16]

forever:
    n = input()
    repeat n:
        values.push(input())
    repeat n:
        minimum = values.extract_min()
        output(minimum)
```


## Case study: Sudoku Auditor

Self-descriptive (hopefully):
```text
program Sudoku

memory masks[27] = 0

forever:
    r = input()
    c = input()
    v = input()
    bit = 1 << (v-1)
    row_index = r
    col_index = c + 9
    box = (r/3)*3 + c/3
    box_index = box + 18
    row_mask = masks[row_index]
    col_mask = masks[col_index]
    box_mask = masks[box_index]
    used = row_mask | col_mask | box_mask
    conflict = used & bit
    new_row_mask = row_mask | bit
    new_col_mask = col_mask | bit
    new_box_mask = box_mask | bit
    one = 1
    zero = 0
    if conflict == 0:
        masks[row_index] = new_row_mask
        masks[col_index] = new_col_mask
        masks[box_index] = new_box_mask
        output(one)
    else:
        output(zero)
```

Each digit is represented by one bit. Slots `0..8` hold row masks, `9..17` hold column masks, and `18..26` hold box masks. A placement is valid when its bit is absent from all three masks.

The backend provides two layouts:
- A combined 27-element mask ring.
- Three separate 9-element row, column, and box rings. This layout is wider but shorter, and spends less ticks.


## Case study: Packet Reassembly

For this problem we use a code-generation intrinsic:
```text
program PacketReassembly
memory window[16] = 0

packet_reassembly(window)
```

In short:

The generated program combines a 16-token ring with a 16-bit presence mask.

The ring head represents the next expected sequence number. A packet is stored at its relative offset; while the low mask bit is set, the head is emitted and both the ring and mask advance. Keeping the head relative to the next expected packet avoids modulo operations.


## Case study: Grade Book

For this problem we alse use a code-generation intrinsic.

The solution supports GET, SET, AVG, and TOP operations over runtime-sized records.

The backend supports two physical layouts:
- A packed ring containing the student ID and four grades in each token.
- Five synchronized rings for IDs and grade columns.

The packed layout uses a single dynamic memory:
```text
program GradeBookPacked
dynamic memory records[16]

gradebook(records)
```

It selects a grade by computing a subject-dependent bit shift. TOP combines the grade and inverse student ID into one comparison key, resolving ties without a second comparison.

The column layout uses five synchronized memories:
```text
program GradeBookColumns
dynamic memory ids[16]
dynamic memory grade1[16]
dynamic memory grade2[16]
dynamic memory grade3[16]
dynamic memory grade4[16]

gradebook(ids, grade1, grade2, grade3, grade4)
```
