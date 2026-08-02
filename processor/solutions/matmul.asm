.memory 96 192
.kind matmul

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
; Registers:
;   r12..r27   B transpose accumulators, then the unpacked current A row
;   r2..r4  N,M,K
;   r5..r11  phase-local counters, addresses, packed values, and sum

start:
  read r2
  read r3
  read r4
  subi r11 r3 2

  ; Pack A row-major, padding every row to sixteen values with encoded zero.
  addi r5 r3 12
  imm r8 0
  mov r6 r2

a_row:
  imm r10 0
  imm r9 1

  .repeat 12 13
    read r0
    addi0 99
    mul0 r9
    add0 r10
    mov r10 r0
    mov r0 r9
    muli0 512
    mov r9 r0
  .endrepeat

  jc r11 a_first_chunk_more
  store r8 r10
  inc r8
  imm r10 0
  store r8 r10
  inc r8
  store r8 r10
  inc r8
  jmp a_row_done

a_first_chunk_more:
  .repeat 14 18
    mov r0 r5
    subi0 {i}
    jc r0 a_read_{i}
    imm r0 99
    jmp a_pack_{i}
    a_read_{i}:
    read r0
    addi0 99
    a_pack_{i}:
    mul0 r9
    add0 r10
    mov r10 r0
    mov r0 r9
    muli0 512
    mov r9 r0
  .endrepeat

  store r8 r10
  inc r8
  imm r10 0
  imm r9 1

  .repeat 19 25
    mov r0 r5
    subi0 {i}
    jc r0 a_read_{i}
    imm r0 99
    jmp a_pack_{i}
    a_read_{i}:
    read r0
    addi0 99
    a_pack_{i}:
    mul0 r9
    add0 r10
    mov r10 r0
    mov r0 r9
    muli0 512
    mov r9 r0
  .endrepeat

  store r8 r10
  inc r8
  imm r10 0
  imm r9 1

  .repeat 26 27
    mov r0 r5
    subi0 {i}
    jc r0 a_read_{i}
    imm r0 99
    jmp a_pack_{i}
    a_read_{i}:
    read r0
    addi0 99
    a_pack_{i}:
    mul0 r9
    add0 r10
    mov r10 r0
    mov r0 r9
    muli0 512
    mov r9 r0
  .endrepeat

  store r8 r10
  inc r8

a_row_done:
  dec r6
  jc r6 a_row

  ; Pack B by columns. The sixteen accumulators transpose each seven-row
  ; chunk while B arrives in row-major order.
  addi r5 r4 12
  mov r6 r3
  imm r7 7
  imm r8 0
  imm r9 1
  .repeat 12 27
    imm r{i} 0
  .endrepeat

b_row:
  .repeat 12 27
    mov r0 r5
    subi0 {i}
    jc r0 b_read_{i}
    jmp b_after_{i}
    b_read_{i}:
    read r0
    addi0 99
    mul0 r9
    add0 r{i}
    mov r{i} r0
    b_after_{i}:
  .endrepeat

  mov r0 r9
  muli0 512
  mov r9 r0
  dec r6
  dec r7
  jc r7 b_chunk_open
  jmp b_flush

b_chunk_open:
  jc r6 b_row

b_flush:
  imm r11 48
  mov r0 r11
  add0 r8
  mov r11 r0
  .repeat 12 27
    store r11 r{i}
    addi r11 r11 3
  .endrepeat

  jc r6 b_next_chunk
  jmp b_loaded

b_next_chunk:
  inc r8
  imm r7 7
  imm r9 1
  .repeat 12 27
    imm r{i} 0
  .endrepeat
  jmp b_row

b_loaded:
  ; Fence the asynchronous stores before reusing the memory.
  imm r11 0
  load r10 r11
  subi r5 r3 2

  ; Decode one A row, then dot it with each packed B column.
  mov r6 r2
  imm r9 0

c_row:
  imm r2 0
  load r10 r9
  inc r9
  .repeat 12 13
    mov r0 r10
    andi0 511
    subi0 99
    mov r{i} r0
    add0 r2
    mov r2 r0
    mov r0 r10
    shri0 9
    mov r10 r0
  .endrepeat

  jc r5 c_row_more
  addi r9 r9 2
  jmp c_row_values_ready

c_row_more:
  .repeat 14 17
    mov r0 r10
    andi0 511
    subi0 99
    mov r{i} r0
    add0 r2
    mov r2 r0
    mov r0 r10
    shri0 9
    mov r10 r0
  .endrepeat
  mov r0 r10
  andi0 511
  subi0 99
  mov r18 r0
  add0 r2
  mov r2 r0

  load r10 r9
  inc r9
  .repeat 19 24
    mov r0 r10
    andi0 511
    subi0 99
    mov r{i} r0
    add0 r2
    mov r2 r0
    mov r0 r10
    shri0 9
    mov r10 r0
  .endrepeat
  mov r0 r10
  andi0 511
  subi0 99
  mov r25 r0
  add0 r2
  mov r2 r0

  load r10 r9
  inc r9
  .repeat 26 26
    mov r0 r10
    andi0 511
    subi0 99
    mov r{i} r0
    add0 r2
    mov r2 r0
    mov r0 r10
    shri0 9
    mov r10 r0
  .endrepeat
  mov r0 r10
  andi0 511
  subi0 99
  mov r27 r0
  add0 r2
  mov r2 r0

c_row_values_ready:
  mov r0 r2
  muli0 99
  mov r2 r0

  mov r7 r4
  imm r8 48

c_column:
  imm r11 0

  load r10 r8
  inc r8
  .repeat 12 13
    mov r0 r10
    andi0 511
    mul0 r{i}
    add0 r11
    mov r11 r0
    mov r0 r10
    shri0 9
    mov r10 r0
  .endrepeat

  jc r5 c_first_chunk_more
  addi r8 r8 2
  jmp c_column_write

c_first_chunk_more:
  .repeat 14 17
    mov r0 r10
    andi0 511
    mul0 r{i}
    add0 r11
    mov r11 r0
    mov r0 r10
    shri0 9
    mov r10 r0
  .endrepeat
  mov r0 r10
  andi0 511
  mul0 r18
  add0 r11
  mov r11 r0

  mov r0 r3
  subi0 7
  jc r0 c_column_more
  addi r8 r8 2
  jmp c_column_write

c_column_more:
  load r10 r8
  inc r8
  .repeat 19 24
    mov r0 r10
    andi0 511
    mul0 r{i}
    add0 r11
    mov r11 r0
    mov r0 r10
    shri0 9
    mov r10 r0
  .endrepeat
  mov r0 r10
  andi0 511
  mul0 r25
  add0 r11
  mov r11 r0

  load r10 r8
  inc r8
  .repeat 26 26
    mov r0 r10
    andi0 511
    mul0 r{i}
    add0 r11
    mov r11 r0
    mov r0 r10
    shri0 9
    mov r10 r0
  .endrepeat
  mov r0 r10
  andi0 511
  mul0 r27
  add0 r11
  mov r11 r0

c_column_write:
  mov r0 r11
  sub0 r2
  mov r11 r0
  write r11
  dec r7
  jc r7 c_column

  dec r6
  jc r6 c_row

halt:
  jmp halt
