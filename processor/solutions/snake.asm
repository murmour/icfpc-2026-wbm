.screen 16 16
.memory 66
.kind snake

; Incremental Snake renderer.
;
; Memory:
;   0..15    one 16-bit occupancy mask per board row
;   16..65   circular queue of position*65536 + occupancy-bit values

.reg head r2      ; packed head position
.reg dir r3       ; direction: 2=up, 3=right, 4=down, 5=left
.reg fruit r4     ; packed fruit position, 256 when absent
.reg queue_tail r5
.reg queue_next r6
.reg work r7      ; shift count / memory address / tail row / loop index
.reg tail r8
.reg next r9      ; command / candidate position
.reg row_addr r10 ; candidate occupancy-row address
.reg bit r11      ; candidate occupancy bit
.reg row_mask r12 ; candidate occupancy-row mask

start:
  jmp initialize

next_round:
  read next
  jeqs next 0 tick
  jeqs next 1 spawn_fruit
  mov dir next
  jmp next_round

spawn_fruit:
  read next
  read row_addr
  mov r0 row_addr
  muli0 16
  add0 next
  mov fruit r0
  screen_addr fruit
  imm r0 9
  screen_data r0
  imm r0 1
  screen_swap r0
  jmp next_round

tick:
  jeqs dir 2 move_up
  jeqs dir 3 move_right
  jeqs dir 4 move_down

move_left:
  mov r0 head
  andi0 15
  jc r0 move_left_valid
  jmp lose

move_left_valid:
  mov r0 head
  subi0 1
  jmp candidate_ready

move_up:
  imm r0 16
  sub0 head
  jc r0 lose
  mov r0 head
  subi0 16
  jmp candidate_ready

move_right:
  mov r0 head
  andi0 15
  subi0 14
  jc r0 lose
  mov r0 head
  addi0 1
  jmp candidate_ready

move_down:
  mov r0 head
  subi0 239
  jc r0 lose
  mov r0 head
  addi0 16

candidate_ready:
  mov next r0

  ; Candidate row.
  divi0 16
  mov row_addr r0

  ; Candidate bit = 32768 >> (15 - x).
  mov r0 next
  andi0 15
  mov work r0
  imm r0 15
  sub0 work
  mov work r0
  imm r0 32768
  shr0 work
  mov bit r0

  load row_mask row_addr

  ; Positions and the absent-fruit sentinel are nonnegative, so XOR can test
  ; equality with one positive-only branch.
  mov r0 next
  xor0 fruit
  jc r0 non_growing

growing:
  mov r0 row_mask
  and0 bit
  jc r0 lose
  imm fruit 256
  jmp add_head

non_growing:
  ; Read and decode the tail queue entry.
  mov r0 queue_tail
  addi0 16
  mov work r0
  load head work

  mov r0 head
  divi0 65536
  mov tail r0

  mov r0 head
  andi0 65535
  mov head r0

  ; Remove the tail before collision testing. This makes moving into the
  ; previous tail cell legal without a special position comparison.
  mov r0 tail
  divi0 16
  mov work r0
  xor0 row_addr
  jc r0 tail_different_row

  mov r0 row_mask
  sub0 head
  mov row_mask r0
  jmp tail_removed

tail_different_row:
  load r0 work
  sub0 head
  store work r0

tail_removed:
  mov r0 row_mask
  and0 bit
  jc r0 lose

  inc queue_tail
  jeqs queue_tail 50 wrap_tail_index
  jmp tail_index_ready

wrap_tail_index:
  imm queue_tail 0

tail_index_ready:

  screen_addr tail
  imm r0 0
  screen_data r0

add_head:
  mov r0 row_mask
  add0 bit
  mov row_mask r0
  store row_addr row_mask

  mov r0 queue_next
  addi0 16
  mov work r0
  mov r0 next
  muli0 65536
  add0 bit
  store work r0

  inc queue_next
  jeqs queue_next 50 wrap_head_index
  jmp head_index_ready

wrap_head_index:
  imm queue_next 0

head_index_ready:

  mov head next
  screen_addr next
  imm r0 10
  screen_data r0
  imm r0 1
  screen_swap r0
  jmp next_round

lose:
  ; Recover the length from the circular queue indices, then recolor the
  ; unchanged snake body in queue order. Equal indices mean a full queue.
  mov r0 queue_next
  sub0 queue_tail
  jc r0 loss_length_ready
  addi0 50

loss_length_ready:
  mov row_mask r0
  mov work queue_tail

lose_loop:
  mov r0 work
  addi0 16
  mov next r0
  load r0 next
  divi0 65536
  screen_addr r0
  imm r0 9
  screen_data r0

  inc work
  jeqs work 50 wrap_loss_index
  jmp loss_index_ready

wrap_loss_index:
  imm work 0

loss_index_ready:
  dec row_mask
  jc row_mask lose_loop
  imm r0 1
  screen_swap r0

halt:
  jmp halt

initialize:
  imm dir 3
  imm fruit 256
  imm queue_tail 0
  imm queue_next 1

  read next
  read row_addr

  mov r0 row_addr
  muli0 16
  add0 next
  mov head r0

  ; Initial occupancy bit = 32768 >> (15 - x).
  imm r0 15
  sub0 next
  mov work r0
  imm r0 32768
  shr0 work
  mov bit r0
  store row_addr bit

  imm work 16
  mov r0 head
  muli0 65536
  add0 bit
  store work r0

  screen_addr head
  imm r0 10
  screen_data r0
  imm r0 1
  screen_swap r0
  jmp next_round
