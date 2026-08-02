.screen 16 16
.kind pathfinder

; RAM-free reverse BFS.
;
; Each group of four registers is a 256-bit row-major board:
;   r30..r33 walls
;   r6..r9   cells still open to the search
;   r2..r5   current frontier
;   r10..r13  next frontier
;   r18..r21  cells whose preferred move is up
;   r22..r25  cells whose preferred move is right
;   r26..r29  cells whose preferred move is down
; r14 is the BFS temporary; r17/r15/r16 hold the robot chunk/bit/offset.
;
; Left is implicit when a visited non-flag cell is in none of the three
; direction masks. Reverse expansion starts at the flag. Processing candidate
; cells in up, right, down, left order assigns the locally preferred move
; among all neighbors one step closer to the flag.

start:
  imm r34 0
  imm r35 1
  imm r37 7
  imm r30 0
  imm r31 0
  imm r32 0
  imm r33 0
  imm r2 0
  imm r3 1
  imm r4 0
  imm r5 0

setup_batch:
  .repeat 0 7
    read r10
    jc r10 setup_wall_{i}

    screen_data r34
    jmp setup_advance_{i}

    setup_wall_{i}:
    mov r0 r2
    add0 r3
    mov r2 r0
    screen_data r37

    setup_advance_{i}:
    mov r0 r3
    muli0 2
    mov r3 r0
  .endrepeat

  mov r0 r4
  addi0 8
  mov r4 r0
  jeqs r4 64 setup_chunk_done
  jmp setup_batch

setup_chunk_done:
  jeqs r5 0 setup_save_wall_0
  jeqs r5 1 setup_save_wall_1
  jeqs r5 2 setup_save_wall_2

setup_save_wall_3:
  mov r33 r2
  jmp setup_board_done

setup_save_wall_0:
  mov r30 r2
  jmp setup_next_chunk

setup_save_wall_1:
  mov r31 r2
  jmp setup_next_chunk

setup_save_wall_2:
  mov r32 r2

setup_next_chunk:
  mov r0 r5
  addi0 1
  mov r5 r0
  imm r2 0
  imm r3 1
  imm r4 0
  jmp setup_batch

setup_board_done:
  read r10
  read r11
  mov r0 r11
  muli0 16
  add0 r10
  mov r36 r0

  ; Build the robot bit once through the shared position-to-bit routine.
  ; The path walker keeps the robot chunk, bit, and offset synchronized.
  mov r13 r36
  imm r29 0
  jmp build_position_bit

setup_robot_bit_ready:

  screen_addr r36
  imm r10 10
  screen_data r10
  screen_swap r35

next_round:
  read r10
  read r11
  mov r0 r11
  muli0 16
  add0 r10
  mov r37 r0

  screen_addr r37
  imm r10 9
  screen_data r10

  ; r6..r9 track cells that are still open to the search. Keeping the
  ; complement of visited avoids complementing it for every expansion.
  mov r0 r30
  xori0 -1
  mov r6 r0
  mov r0 r31
  xori0 -1
  mov r7 r0
  mov r0 r32
  xori0 -1
  mov r8 r0
  mov r0 r33
  xori0 -1
  mov r9 r0
  imm r2 0
  imm r3 0
  imm r4 0
  imm r5 0
  imm r10 0
  imm r11 0
  imm r12 0
  imm r13 0
  imm r18 0
  imm r19 0
  imm r20 0
  imm r21 0
  imm r22 0
  imm r23 0
  imm r24 0
  imm r25 0
  imm r26 0
  imm r27 0
  imm r28 0
  imm r29 0

  ; Shared position-to-bit conversion. r29 selects the flag continuation;
  ; setup enters with zero and copies the result into the robot state.
  mov r13 r37
  imm r29 1

build_position_bit:
  mov r0 r13
  divi0 64
  mov r10 r0
  muli0 64
  mov r14 r0
  mov r0 r13
  sub0 r14
  mov r12 r0
  imm r11 1
  mov r0 r12
  andi0 1
  jc r0 flag_bit_mul_1
  jmp flag_bit_after_1

flag_bit_mul_1:
  mov r0 r11
  muli0 2
  mov r11 r0

flag_bit_after_1:
  mov r0 r12
  andi0 2
  jc r0 flag_bit_mul_2
  jmp flag_bit_after_2

flag_bit_mul_2:
  mov r0 r11
  muli0 4
  mov r11 r0

flag_bit_after_2:
  mov r0 r12
  andi0 4
  jc r0 flag_bit_mul_4
  jmp flag_bit_after_4

flag_bit_mul_4:
  mov r0 r11
  muli0 16
  mov r11 r0

flag_bit_after_4:
  mov r0 r12
  andi0 8
  jc r0 flag_bit_mul_8
  jmp flag_bit_after_8

flag_bit_mul_8:
  mov r0 r11
  muli0 256
  mov r11 r0

flag_bit_after_8:
  mov r0 r12
  andi0 16
  jc r0 flag_bit_mul_16
  jmp flag_bit_after_16

flag_bit_mul_16:
  mov r0 r11
  muli0 65536
  mov r11 r0

flag_bit_after_16:
  mov r0 r12
  andi0 32
  jc r0 flag_bit_mul_32
  jmp flag_bit_ready

flag_bit_mul_32:
  mov r0 r11
  muli0 4294967296
  mov r11 r0

flag_bit_ready:
  jc r29 flag_bit_dispatch
  mov r17 r10
  mov r15 r11
  mov r16 r12
  jmp setup_robot_bit_ready

flag_bit_dispatch:
  imm r29 0
  mov r0 r10
  subi0 1
  jc r0 seed_flag_high
  mov r0 r10
  jc r0 seed_flag_1
  jmp seed_flag_0

seed_flag_high:
  mov r0 r10
  subi0 2
  jc r0 seed_flag_3
  jmp seed_flag_2

seed_flag_3:
  mov r5 r11
  mov r0 r9
  xor0 r11
  mov r9 r0
  jmp bfs_layer

seed_flag_0:
  mov r2 r11
  mov r0 r6
  xor0 r11
  mov r6 r0
  jmp bfs_layer

seed_flag_1:
  mov r3 r11
  mov r0 r7
  xor0 r11
  mov r7 r0
  jmp bfs_layer

seed_flag_2:
  mov r4 r11
  mov r0 r8
  xor0 r11
  mov r8 r0

bfs_layer:
  imm r10 0
  imm r11 0
  imm r12 0
  imm r13 0

  ; Preferred move UP: candidate cells are one row below the frontier.
  mov r0 r2
  jc r0 up_compute_0
  jmp up_done_0

up_compute_0:
  mov r0 r2
  muli0 65536
  and0 r6
  jc r0 up_apply_0
  jmp up_done_0

up_apply_0:
  mov r14 r0
  xor0 r6
  mov r6 r0
  mov r0 r10
  add0 r14
  mov r10 r0
  mov r0 r18
  add0 r14
  mov r18 r0

up_done_0:

  mov r0 r3
  jc r0 up_compute_1
  mov r0 r2
  jc r0 up_compute_1
  jmp up_done_1

up_compute_1:
  mov r0 r3
  muli0 65536
  mov r14 r0
  mov r0 r2
  shri0 48
  add0 r14
  and0 r7
  jc r0 up_apply_1
  jmp up_done_1

up_apply_1:
  mov r14 r0
  xor0 r7
  mov r7 r0
  mov r0 r11
  add0 r14
  mov r11 r0
  mov r0 r19
  add0 r14
  mov r19 r0

up_done_1:

  mov r0 r4
  jc r0 up_compute_2
  mov r0 r3
  jc r0 up_compute_2
  jmp up_done_2

up_compute_2:
  mov r0 r4
  muli0 65536
  mov r14 r0
  mov r0 r3
  shri0 48
  add0 r14
  and0 r8
  jc r0 up_apply_2
  jmp up_done_2

up_apply_2:
  mov r14 r0
  xor0 r8
  mov r8 r0
  mov r0 r12
  add0 r14
  mov r12 r0
  mov r0 r20
  add0 r14
  mov r20 r0

up_done_2:

  mov r0 r5
  jc r0 up_compute_3
  mov r0 r4
  jc r0 up_compute_3
  jmp up_done_3

up_compute_3:
  mov r0 r5
  muli0 65536
  mov r14 r0
  mov r0 r4
  shri0 48
  add0 r14
  and0 r9
  jc r0 up_apply_3
  jmp up_done_3

up_apply_3:
  mov r14 r0
  xor0 r9
  mov r9 r0
  mov r0 r13
  add0 r14
  mov r13 r0
  mov r0 r21
  add0 r14
  mov r21 r0

up_done_3:

  ; Preferred move RIGHT: candidate cells are one column left.
  mov r0 r2
  jc r0 right_compute_0
  jmp right_done_0

right_compute_0:
  mov r0 r2
  shri0 1
  and0 r6
  jc r0 right_apply_0
  jmp right_done_0

right_apply_0:
  mov r14 r0
  xor0 r6
  mov r6 r0
  mov r0 r10
  add0 r14
  mov r10 r0
  mov r0 r22
  add0 r14
  mov r22 r0

right_done_0:

  mov r0 r3
  jc r0 right_compute_1
  jmp right_done_1

right_compute_1:
  mov r0 r3
  shri0 1
  and0 r7
  jc r0 right_apply_1
  jmp right_done_1

right_apply_1:
  mov r14 r0
  xor0 r7
  mov r7 r0
  mov r0 r11
  add0 r14
  mov r11 r0
  mov r0 r23
  add0 r14
  mov r23 r0

right_done_1:
  mov r0 r4
  jc r0 right_compute_2
  jmp right_done_2

right_compute_2:
  mov r0 r4
  shri0 1
  and0 r8
  jc r0 right_apply_2
  jmp right_done_2

right_apply_2:
  mov r14 r0
  xor0 r8
  mov r8 r0
  mov r0 r12
  add0 r14
  mov r12 r0
  mov r0 r24
  add0 r14
  mov r24 r0

right_done_2:
  mov r0 r5
  jc r0 right_compute_3
  jmp right_done_3

right_compute_3:
  mov r0 r5
  shri0 1
  and0 r9
  jc r0 right_apply_3
  jmp right_done_3

right_apply_3:
  mov r14 r0
  xor0 r9
  mov r9 r0
  mov r0 r13
  add0 r14
  mov r13 r0
  mov r0 r25
  add0 r14
  mov r25 r0

right_done_3:
  ; Preferred move DOWN: candidate cells are one row above the frontier.
  mov r0 r2
  jc r0 down_compute_0
  mov r0 r3
  jc r0 down_compute_0
  jmp down_done_0

down_compute_0:
  mov r0 r2
  shri0 16
  mov r14 r0
  mov r0 r3
  andi0 65535
  muli0 281474976710656
  add0 r14
  and0 r6
  jc r0 down_apply_0
  jmp down_done_0

down_apply_0:
  mov r14 r0
  xor0 r6
  mov r6 r0
  mov r0 r10
  add0 r14
  mov r10 r0
  mov r0 r26
  add0 r14
  mov r26 r0

down_done_0:
  mov r0 r3
  jc r0 down_compute_1
  mov r0 r4
  jc r0 down_compute_1
  jmp down_done_1

down_compute_1:
  mov r0 r3
  shri0 16
  mov r14 r0
  mov r0 r4
  andi0 65535
  muli0 281474976710656
  add0 r14
  and0 r7
  jc r0 down_apply_1
  jmp down_done_1

down_apply_1:
  mov r14 r0
  xor0 r7
  mov r7 r0
  mov r0 r11
  add0 r14
  mov r11 r0
  mov r0 r27
  add0 r14
  mov r27 r0

down_done_1:
  mov r0 r4
  jc r0 down_compute_2
  mov r0 r5
  jc r0 down_compute_2
  jmp down_done_2

down_compute_2:
  mov r0 r4
  shri0 16
  mov r14 r0
  mov r0 r5
  andi0 65535
  muli0 281474976710656
  add0 r14
  and0 r8
  jc r0 down_apply_2
  jmp down_done_2

down_apply_2:
  mov r14 r0
  xor0 r8
  mov r8 r0
  mov r0 r12
  add0 r14
  mov r12 r0
  mov r0 r28
  add0 r14
  mov r28 r0

down_done_2:
  mov r0 r5
  jc r0 down_compute_3
  jmp down_done_3

down_compute_3:
  mov r0 r5
  shri0 16
  and0 r9
  jc r0 down_apply_3
  jmp down_done_3

down_apply_3:
  mov r14 r0
  xor0 r9
  mov r9 r0
  mov r0 r13
  add0 r14
  mov r13 r0
  mov r0 r29
  add0 r14
  mov r29 r0

down_done_3:
  ; Preferred move LEFT is implicit: candidate cells are one column right.
  mov r0 r2
  jc r0 left_compute_0
  jmp left_done_0

left_compute_0:
  mov r0 r2
  muli0 2
  and0 r6
  jc r0 left_apply_0
  jmp left_done_0

left_apply_0:
  mov r14 r0
  xor0 r6
  mov r6 r0
  mov r0 r10
  add0 r14
  mov r10 r0

left_done_0:
  mov r0 r3
  jc r0 left_compute_1
  jmp left_done_1

left_compute_1:
  mov r0 r3
  muli0 2
  and0 r7
  jc r0 left_apply_1
  jmp left_done_1

left_apply_1:
  mov r14 r0
  xor0 r7
  mov r7 r0
  mov r0 r11
  add0 r14
  mov r11 r0

left_done_1:
  mov r0 r4
  jc r0 left_compute_2
  jmp left_done_2

left_compute_2:
  mov r0 r4
  muli0 2
  and0 r8
  jc r0 left_apply_2
  jmp left_done_2

left_apply_2:
  mov r14 r0
  xor0 r8
  mov r8 r0
  mov r0 r12
  add0 r14
  mov r12 r0

left_done_2:
  mov r0 r5
  jc r0 left_compute_3
  jmp left_done_3

left_compute_3:
  mov r0 r5
  muli0 2
  and0 r9
  jc r0 left_apply_3
  jmp left_done_3

left_apply_3:
  mov r14 r0
  xor0 r9
  mov r9 r0
  mov r0 r13
  add0 r14
  mov r13 r0

left_done_3:
  mov r2 r10
  mov r3 r11
  mov r4 r12
  mov r5 r13
  mov r0 r17
  subi0 1
  jc r0 bfs_check_robot_high
  mov r0 r17
  jc r0 bfs_check_robot_1
  jmp bfs_check_robot_0

bfs_check_robot_high:
  mov r0 r17
  subi0 2
  jc r0 bfs_check_robot_3
  jmp bfs_check_robot_2

bfs_check_robot_3:
  mov r0 r5
  and0 r15
  jc r0 path_ready
  jmp bfs_layer

bfs_check_robot_0:
  mov r0 r2
  and0 r15
  jc r0 path_ready
  jmp bfs_layer

bfs_check_robot_1:
  mov r0 r3
  and0 r15
  jc r0 path_ready
  jmp bfs_layer

bfs_check_robot_2:
  mov r0 r4
  and0 r15
  jc r0 path_ready
  jmp bfs_layer

path_ready:
  imm r10 10

path_step:
  ; Test the three explicit direction masks for the robot's current bit.
  mov r0 r17
  subi0 1
  jc r0 path_chunk_high
  mov r0 r17
  jc r0 path_chunk_1
  jmp path_chunk_0

path_chunk_high:
  mov r0 r17
  subi0 2
  jc r0 path_chunk_3
  jmp path_chunk_2

path_chunk_3:
  mov r0 r21
  and0 r15
  jc r0 move_up
  mov r0 r25
  and0 r15
  jc r0 move_right
  mov r0 r29
  and0 r15
  jc r0 move_down
  jmp move_left

path_chunk_0:
  mov r0 r18
  and0 r15
  jc r0 move_up
  mov r0 r22
  and0 r15
  jc r0 move_right
  mov r0 r26
  and0 r15
  jc r0 move_down
  jmp move_left

path_chunk_1:
  mov r0 r19
  and0 r15
  jc r0 move_up
  mov r0 r23
  and0 r15
  jc r0 move_right
  mov r0 r27
  and0 r15
  jc r0 move_down
  jmp move_left

path_chunk_2:
  mov r0 r20
  and0 r15
  jc r0 move_up
  mov r0 r24
  and0 r15
  jc r0 move_right
  mov r0 r28
  and0 r15
  jc r0 move_down

move_left:
  mov r14 r36
  mov r0 r36
  subi0 1
  mov r36 r0
  mov r0 r16
  subi0 1
  mov r16 r0
  mov r0 r15
  divi0 2
  mov r15 r0
  jmp move_draw

move_up:
  mov r14 r36
  mov r0 r36
  subi0 16
  mov r36 r0
  mov r0 r16
  subi0 15
  jc r0 move_up_same_chunk
  mov r0 r17
  subi0 1
  mov r17 r0
  mov r0 r16
  addi0 48
  mov r16 r0
  mov r0 r15
  muli0 281474976710656
  mov r15 r0
  jmp move_draw

move_up_same_chunk:
  mov r0 r16
  subi0 16
  mov r16 r0
  mov r0 r15
  divi0 65536
  mov r15 r0
  jmp move_draw

move_right:
  mov r14 r36
  mov r0 r36
  addi0 1
  mov r36 r0
  mov r0 r16
  addi0 1
  mov r16 r0
  mov r0 r15
  muli0 2
  mov r15 r0
  jmp move_draw

move_down:
  mov r14 r36
  mov r0 r36
  addi0 16
  mov r36 r0
  mov r0 r16
  subi0 47
  jc r0 move_down_next_chunk
  mov r0 r16
  addi0 16
  mov r16 r0
  mov r0 r15
  muli0 65536
  mov r15 r0
  jmp move_draw

move_down_next_chunk:
  mov r0 r17
  addi0 1
  mov r17 r0
  mov r0 r16
  subi0 48
  mov r16 r0
  mov r0 r15
  divi0 281474976710656
  mov r15 r0

move_draw:
  screen_addr r14
  screen_data r34
  screen_addr r36
  screen_data r10
  screen_swap r35
  jeqrs r36 r37 next_round
  jmp path_step
