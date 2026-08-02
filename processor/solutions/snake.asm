.screen 16 16
.memory 66
.kind snake

; Incremental Snake renderer.
;
; Memory:
;   0..15    one 16-bit occupancy mask per board row
;   16..65   circular queue of position*65536 + occupancy-bit values
;
; Registers:
;   r0,r1    ALU and immediate scratch
;   r2       packed head position
;   r3       direction: 2=up, 3=right, 4=down, 5=left
;   r4       packed fruit position, 256 when absent
;   r5,r6    tail and next queue indices
;   r7       shift count / memory address / tail row / loop index
;   r8       tail position
;   r9       command / candidate position
;   r10      candidate occupancy-row address
;   r11      candidate occupancy bit
;   r12      candidate occupancy-row mask

start:
  jmp initialize

next_round:
  read r9
  jeqs r9 0 tick
  jeqs r9 1 spawn_fruit
  mov r3 r9
  jmp next_round

spawn_fruit:
  read r9
  read r10
  mov r0 r10
  muli0 16
  add0 r9
  mov r4 r0
  screen_addr r4
  imm r0 9
  screen_data r0
  imm r0 1
  screen_swap r0
  jmp next_round

tick:
  jeqs r3 2 move_up
  jeqs r3 3 move_right
  jeqs r3 4 move_down

move_left:
  mov r0 r2
  andi0 15
  jc r0 move_left_valid
  jmp lose

move_left_valid:
  mov r0 r2
  subi0 1
  jmp candidate_ready

move_up:
  imm r0 16
  sub0 r2
  jc r0 lose
  mov r0 r2
  subi0 16
  jmp candidate_ready

move_right:
  mov r0 r2
  andi0 15
  subi0 14
  jc r0 lose
  mov r0 r2
  addi0 1
  jmp candidate_ready

move_down:
  mov r0 r2
  subi0 239
  jc r0 lose
  mov r0 r2
  addi0 16

candidate_ready:
  mov r9 r0

  ; Candidate row.
  divi0 16
  mov r10 r0

  ; Candidate bit = 32768 >> (15 - x).
  mov r0 r9
  andi0 15
  mov r7 r0
  imm r0 15
  sub0 r7
  mov r7 r0
  imm r0 32768
  shr0 r7
  mov r11 r0

  load r12 r10

  ; Positions and the absent-fruit sentinel are nonnegative, so XOR can test
  ; equality with one positive-only branch.
  mov r0 r9
  xor0 r4
  jc r0 non_growing

growing:
  mov r0 r12
  and0 r11
  jc r0 lose
  imm r4 256
  jmp add_head

non_growing:
  ; Read and decode the tail queue entry.
  mov r0 r5
  addi0 16
  mov r7 r0
  load r2 r7

  mov r0 r2
  divi0 65536
  mov r8 r0

  mov r0 r2
  andi0 65535
  mov r2 r0

  ; Remove the tail before collision testing. This makes moving into the
  ; previous tail cell legal without a special position comparison.
  mov r0 r8
  divi0 16
  mov r7 r0
  xor0 r10
  jc r0 tail_different_row

  mov r0 r12
  sub0 r2
  mov r12 r0
  jmp tail_removed

tail_different_row:
  load r0 r7
  sub0 r2
  store r7 r0

tail_removed:
  mov r0 r12
  and0 r11
  jc r0 lose

  inc r5
  jeqs r5 50 wrap_tail_index
  jmp tail_index_ready

wrap_tail_index:
  imm r5 0

tail_index_ready:

  screen_addr r8
  imm r0 0
  screen_data r0

add_head:
  mov r0 r12
  add0 r11
  mov r12 r0
  store r10 r12

  mov r0 r6
  addi0 16
  mov r7 r0
  mov r0 r9
  muli0 65536
  add0 r11
  store r7 r0

  inc r6
  jeqs r6 50 wrap_head_index
  jmp head_index_ready

wrap_head_index:
  imm r6 0

head_index_ready:

  mov r2 r9
  screen_addr r9
  imm r0 10
  screen_data r0
  imm r0 1
  screen_swap r0
  jmp next_round

lose:
  ; Recover the length from the circular queue indices, then recolor the
  ; unchanged snake body in queue order. Equal indices mean a full queue.
  mov r0 r6
  sub0 r5
  jc r0 loss_length_ready
  addi0 50

loss_length_ready:
  mov r12 r0
  mov r7 r5

lose_loop:
  mov r0 r7
  addi0 16
  mov r9 r0
  load r0 r9
  divi0 65536
  screen_addr r0
  imm r0 9
  screen_data r0

  inc r7
  jeqs r7 50 wrap_loss_index
  jmp loss_index_ready

wrap_loss_index:
  imm r7 0

loss_index_ready:
  dec r12
  jc r12 lose_loop
  imm r0 1
  screen_swap r0

halt:
  jmp halt

initialize:
  imm r3 3
  imm r4 256
  imm r5 0
  imm r6 1

  read r9
  read r10

  mov r0 r10
  muli0 16
  add0 r9
  mov r2 r0

  ; Initial occupancy bit = 32768 >> (15 - x).
  imm r0 15
  sub0 r9
  mov r7 r0
  imm r0 32768
  shr0 r7
  mov r11 r0
  store r10 r11

  imm r7 16
  mov r0 r2
  muli0 65536
  add0 r11
  store r7 r0

  screen_addr r2
  imm r0 10
  screen_data r0
  imm r0 1
  screen_swap r0
  jmp next_round
