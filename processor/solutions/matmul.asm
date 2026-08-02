.memory 96 192
.kind matmul

.reg n r2
.reg bias r2
.reg m r3
.reg k r4
.reg limit r5
.reg rows r6
.reg count r7
.reg addr r8
.reg factor r9
.reg packed r10
.reg sum r11

.repeat 12 27
  .reg value{i} r{i}
.endrepeat

; Packed CPU matrix multiplication.
;
; Values are encoded as value+99 and packed in 9-bit fields. Seven fields
; fit in one positive signed 64-bit word, so every row of A and every
; transposed column of B occupies three RAM words.
;
; RAM:
;    0..47  A, three packed words per row
;   48..95  transposed B, three packed words per column
;
; `n` becomes the encoded-row `bias` after the row count has been copied.
; `value12` through `value27` first transpose B, then hold one unpacked A row.

start:
  read n
  read m
  read k
  subi sum m 2

  ; Pack A row-major, padding every row to sixteen values with encoded zero.
  addi limit m 12
  imm addr 0
  mov rows n

a_row:
  imm packed 0
  imm factor 1

  .repeat 12 13
    read r0
    addi0 99
    mul0 factor
    add0 packed
    mov packed r0
    mov r0 factor
    muli0 512
    mov factor r0
  .endrepeat

  jc sum a_first_chunk_more
  store addr packed
  inc addr
  imm packed 0
  store addr packed
  inc addr
  store addr packed
  inc addr
  jmp a_row_done

a_first_chunk_more:
  .repeat 14 18
    mov r0 limit
    subi0 {i}
    jc r0 a_read_{i}
    imm r0 99
    jmp a_pack_{i}
    a_read_{i}:
    read r0
    addi0 99
    a_pack_{i}:
    mul0 factor
    add0 packed
    mov packed r0
    mov r0 factor
    muli0 512
    mov factor r0
  .endrepeat

  store addr packed
  inc addr
  imm packed 0
  imm factor 1

  .repeat 19 25
    mov r0 limit
    subi0 {i}
    jc r0 a_read_{i}
    imm r0 99
    jmp a_pack_{i}
    a_read_{i}:
    read r0
    addi0 99
    a_pack_{i}:
    mul0 factor
    add0 packed
    mov packed r0
    mov r0 factor
    muli0 512
    mov factor r0
  .endrepeat

  store addr packed
  inc addr
  imm packed 0
  imm factor 1

  .repeat 26 27
    mov r0 limit
    subi0 {i}
    jc r0 a_read_{i}
    imm r0 99
    jmp a_pack_{i}
    a_read_{i}:
    read r0
    addi0 99
    a_pack_{i}:
    mul0 factor
    add0 packed
    mov packed r0
    mov r0 factor
    muli0 512
    mov factor r0
  .endrepeat

  store addr packed
  inc addr

a_row_done:
  dec rows
  jc rows a_row

  ; Pack B by columns. The sixteen accumulators transpose each seven-row
  ; chunk while B arrives in row-major order.
  addi limit k 12
  mov rows m
  imm count 7
  imm addr 0
  imm factor 1
  .repeat 12 27
    imm value{i} 0
  .endrepeat

b_row:
  .repeat 12 27
    mov r0 limit
    subi0 {i}
    jc r0 b_read_{i}
    jmp b_after_{i}
    b_read_{i}:
    read r0
    addi0 99
    mul0 factor
    add0 value{i}
    mov value{i} r0
    b_after_{i}:
  .endrepeat

  mov r0 factor
  muli0 512
  mov factor r0
  dec rows
  dec count
  jc count b_chunk_open
  jmp b_flush

b_chunk_open:
  jc rows b_row

b_flush:
  imm sum 48
  mov r0 sum
  add0 addr
  mov sum r0
  .repeat 12 27
    store sum value{i}
    addi sum sum 3
  .endrepeat

  jc rows b_next_chunk
  jmp b_loaded

b_next_chunk:
  inc addr
  imm count 7
  imm factor 1
  .repeat 12 27
    imm value{i} 0
  .endrepeat
  jmp b_row

b_loaded:
  ; Fence the asynchronous stores before reusing the memory.
  imm sum 0
  load packed sum
  subi limit m 2

  ; Decode one A row, then dot it with each packed B column.
  mov rows n
  imm factor 0

c_row:
  imm bias 0
  load packed factor
  inc factor
  .repeat 12 13
    mov r0 packed
    andi0 511
    subi0 99
    mov value{i} r0
    add0 bias
    mov bias r0
    mov r0 packed
    shri0 9
    mov packed r0
  .endrepeat

  jc limit c_row_more
  addi factor factor 2
  jmp c_row_values_ready

c_row_more:
  .repeat 14 17
    mov r0 packed
    andi0 511
    subi0 99
    mov value{i} r0
    add0 bias
    mov bias r0
    mov r0 packed
    shri0 9
    mov packed r0
  .endrepeat
  mov r0 packed
  andi0 511
  subi0 99
  mov value18 r0
  add0 bias
  mov bias r0

  load packed factor
  inc factor
  .repeat 19 24
    mov r0 packed
    andi0 511
    subi0 99
    mov value{i} r0
    add0 bias
    mov bias r0
    mov r0 packed
    shri0 9
    mov packed r0
  .endrepeat
  mov r0 packed
  andi0 511
  subi0 99
  mov value25 r0
  add0 bias
  mov bias r0

  load packed factor
  inc factor
  .repeat 26 26
    mov r0 packed
    andi0 511
    subi0 99
    mov value{i} r0
    add0 bias
    mov bias r0
    mov r0 packed
    shri0 9
    mov packed r0
  .endrepeat
  mov r0 packed
  andi0 511
  subi0 99
  mov value27 r0
  add0 bias
  mov bias r0

c_row_values_ready:
  mov r0 bias
  muli0 99
  mov bias r0

  mov count k
  imm addr 48

c_column:
  imm sum 0

  load packed addr
  inc addr
  .repeat 12 13
    mov r0 packed
    andi0 511
    mul0 value{i}
    add0 sum
    mov sum r0
    mov r0 packed
    shri0 9
    mov packed r0
  .endrepeat

  jc limit c_first_chunk_more
  addi addr addr 2
  jmp c_column_write

c_first_chunk_more:
  .repeat 14 17
    mov r0 packed
    andi0 511
    mul0 value{i}
    add0 sum
    mov sum r0
    mov r0 packed
    shri0 9
    mov packed r0
  .endrepeat
  mov r0 packed
  andi0 511
  mul0 value18
  add0 sum
  mov sum r0

  mov r0 m
  subi0 7
  jc r0 c_column_more
  addi addr addr 2
  jmp c_column_write

c_column_more:
  load packed addr
  inc addr
  .repeat 19 24
    mov r0 packed
    andi0 511
    mul0 value{i}
    add0 sum
    mov sum r0
    mov r0 packed
    shri0 9
    mov packed r0
  .endrepeat
  mov r0 packed
  andi0 511
  mul0 value25
  add0 sum
  mov sum r0

  load packed addr
  inc addr
  .repeat 26 26
    mov r0 packed
    andi0 511
    mul0 value{i}
    add0 sum
    mov sum r0
    mov r0 packed
    shri0 9
    mov packed r0
  .endrepeat
  mov r0 packed
  andi0 511
  mul0 value27
  add0 sum
  mov sum r0

c_column_write:
  mov r0 sum
  sub0 bias
  mov sum r0
  write sum
  dec count
  jc count c_column

  dec rows
  jc rows c_row

halt:
  jmp halt
