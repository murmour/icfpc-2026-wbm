.screen 16 16
.kind pathfinder

.reg frontier[4] r2
.reg open[4] r6
.reg next[4] r10
.reg temp r14
.reg robot_bit r15
.reg robot_offset r16
.reg robot_chunk r17
.reg up[4] r18
.reg right[4] r22
.reg down[4] r26
.reg bit_dispatch r29
.reg walls[4] r30
.reg black r34
.reg one r35
.reg robot_pos r36
; The wall color slot becomes the flag position after setup.
.reg wall_color r37
.reg flag_pos r37

; RAM-free reverse BFS.
;
; Each group of four registers is a 256-bit row-major board:
;   walls       obstacles
;   open        cells still open to the search
;   frontier    current frontier
;   next        next frontier
;   up/right/down  cells whose preferred move has that direction
; `temp` is BFS scratch; the robot's chunk, bit, and offset track its position.
;
; Left is implicit when a visited non-flag cell is in none of the three
; direction masks. Reverse expansion starts at the flag. Processing candidate
; cells in up, right, down, left order assigns the locally preferred move
; among all neighbors one step closer to the flag.

start:
  imm black 0
  imm one 1
  imm wall_color 7
  imm walls[0] 0
  imm walls[1] 0
  imm walls[2] 0
  imm walls[3] 0
  imm frontier[0] 0
  imm frontier[1] 1
  imm frontier[2] 0
  imm frontier[3] 0

setup_batch:
  .repeat 0 7
    read next[0]
    jc next[0] setup_wall_{i}

    screen_data black
    jmp setup_advance_{i}

    setup_wall_{i}:
    mov r0 frontier[0]
    add0 frontier[1]
    mov frontier[0] r0
    screen_data wall_color

    setup_advance_{i}:
    mov r0 frontier[1]
    muli0 2
    mov frontier[1] r0
  .endrepeat

  mov r0 frontier[2]
  addi0 8
  mov frontier[2] r0
  jeqs frontier[2] 64 setup_chunk_done
  jmp setup_batch

setup_chunk_done:
  jeqs frontier[3] 0 setup_save_wall_0
  jeqs frontier[3] 1 setup_save_wall_1
  jeqs frontier[3] 2 setup_save_wall_2

setup_save_wall_3:
  mov walls[3] frontier[0]
  jmp setup_board_done

setup_save_wall_0:
  mov walls[0] frontier[0]
  jmp setup_next_chunk

setup_save_wall_1:
  mov walls[1] frontier[0]
  jmp setup_next_chunk

setup_save_wall_2:
  mov walls[2] frontier[0]

setup_next_chunk:
  mov r0 frontier[3]
  addi0 1
  mov frontier[3] r0
  imm frontier[0] 0
  imm frontier[1] 1
  imm frontier[2] 0
  jmp setup_batch

setup_board_done:
  read next[0]
  read next[1]
  mov r0 next[1]
  muli0 16
  add0 next[0]
  mov robot_pos r0

  ; Build the robot bit once through the shared position-to-bit routine.
  ; The path walker keeps the robot chunk, bit, and offset synchronized.
  mov next[3] robot_pos
  imm bit_dispatch 0
  jmp build_position_bit

setup_robot_bit_ready:

  screen_addr robot_pos
  imm next[0] 10
  screen_data next[0]
  screen_swap one

next_round:
  read next[0]
  read next[1]
  mov r0 next[1]
  muli0 16
  add0 next[0]
  mov flag_pos r0

  screen_addr flag_pos
  imm next[0] 9
  screen_data next[0]

  ; open[0]..open[3] track cells that are still open to the search. Keeping the
  ; complement of visited avoids complementing it for every expansion.
  mov r0 walls[0]
  xori0 -1
  mov open[0] r0
  mov r0 walls[1]
  xori0 -1
  mov open[1] r0
  mov r0 walls[2]
  xori0 -1
  mov open[2] r0
  mov r0 walls[3]
  xori0 -1
  mov open[3] r0
  imm frontier[0] 0
  imm frontier[1] 0
  imm frontier[2] 0
  imm frontier[3] 0
  imm next[0] 0
  imm next[1] 0
  imm next[2] 0
  imm next[3] 0
  imm up[0] 0
  imm up[1] 0
  imm up[2] 0
  imm up[3] 0
  imm right[0] 0
  imm right[1] 0
  imm right[2] 0
  imm right[3] 0
  imm down[0] 0
  imm down[1] 0
  imm down[2] 0
  imm down[3] 0

  ; Shared position-to-bit conversion. bit_dispatch selects the flag
  ; continuation; setup enters with zero and copies the result into the robot.
  mov next[3] flag_pos
  imm bit_dispatch 1

build_position_bit:
  mov r0 next[3]
  divi0 64
  mov next[0] r0
  muli0 64
  mov temp r0
  mov r0 next[3]
  sub0 temp
  mov next[2] r0
  imm next[1] 1
  mov r0 next[2]
  andi0 1
  jc r0 flag_bit_mul_1
  jmp flag_bit_after_1

flag_bit_mul_1:
  mov r0 next[1]
  muli0 2
  mov next[1] r0

flag_bit_after_1:
  mov r0 next[2]
  andi0 2
  jc r0 flag_bit_mul_2
  jmp flag_bit_after_2

flag_bit_mul_2:
  mov r0 next[1]
  muli0 4
  mov next[1] r0

flag_bit_after_2:
  mov r0 next[2]
  andi0 4
  jc r0 flag_bit_mul_4
  jmp flag_bit_after_4

flag_bit_mul_4:
  mov r0 next[1]
  muli0 16
  mov next[1] r0

flag_bit_after_4:
  mov r0 next[2]
  andi0 8
  jc r0 flag_bit_mul_8
  jmp flag_bit_after_8

flag_bit_mul_8:
  mov r0 next[1]
  muli0 256
  mov next[1] r0

flag_bit_after_8:
  mov r0 next[2]
  andi0 16
  jc r0 flag_bit_mul_16
  jmp flag_bit_after_16

flag_bit_mul_16:
  mov r0 next[1]
  muli0 65536
  mov next[1] r0

flag_bit_after_16:
  mov r0 next[2]
  andi0 32
  jc r0 flag_bit_mul_32
  jmp flag_bit_ready

flag_bit_mul_32:
  mov r0 next[1]
  muli0 4294967296
  mov next[1] r0

flag_bit_ready:
  jc bit_dispatch flag_bit_dispatch
  mov robot_chunk next[0]
  mov robot_bit next[1]
  mov robot_offset next[2]
  jmp setup_robot_bit_ready

flag_bit_dispatch:
  imm bit_dispatch 0
  mov r0 next[0]
  subi0 1
  jc r0 seed_flag_high
  mov r0 next[0]
  jc r0 seed_flag_1
  jmp seed_flag_0

seed_flag_high:
  mov r0 next[0]
  subi0 2
  jc r0 seed_flag_3
  jmp seed_flag_2

seed_flag_3:
  mov frontier[3] next[1]
  mov r0 open[3]
  xor0 next[1]
  mov open[3] r0
  jmp bfs_layer

seed_flag_0:
  mov frontier[0] next[1]
  mov r0 open[0]
  xor0 next[1]
  mov open[0] r0
  jmp bfs_layer

seed_flag_1:
  mov frontier[1] next[1]
  mov r0 open[1]
  xor0 next[1]
  mov open[1] r0
  jmp bfs_layer

seed_flag_2:
  mov frontier[2] next[1]
  mov r0 open[2]
  xor0 next[1]
  mov open[2] r0

bfs_layer:
  imm next[0] 0
  imm next[1] 0
  imm next[2] 0
  imm next[3] 0

  ; Preferred move UP: candidate cells are one row below the frontier.
  mov r0 frontier[0]
  jc r0 up_compute_0
  jmp up_done_0

up_compute_0:
  mov r0 frontier[0]
  muli0 65536
  and0 open[0]
  jc r0 up_apply_0
  jmp up_done_0

up_apply_0:
  mov temp r0
  xor0 open[0]
  mov open[0] r0
  mov r0 next[0]
  add0 temp
  mov next[0] r0
  mov r0 up[0]
  add0 temp
  mov up[0] r0

up_done_0:

  mov r0 frontier[1]
  jc r0 up_compute_1
  mov r0 frontier[0]
  jc r0 up_compute_1
  jmp up_done_1

up_compute_1:
  mov r0 frontier[1]
  muli0 65536
  mov temp r0
  mov r0 frontier[0]
  shri0 48
  add0 temp
  and0 open[1]
  jc r0 up_apply_1
  jmp up_done_1

up_apply_1:
  mov temp r0
  xor0 open[1]
  mov open[1] r0
  mov r0 next[1]
  add0 temp
  mov next[1] r0
  mov r0 up[1]
  add0 temp
  mov up[1] r0

up_done_1:

  mov r0 frontier[2]
  jc r0 up_compute_2
  mov r0 frontier[1]
  jc r0 up_compute_2
  jmp up_done_2

up_compute_2:
  mov r0 frontier[2]
  muli0 65536
  mov temp r0
  mov r0 frontier[1]
  shri0 48
  add0 temp
  and0 open[2]
  jc r0 up_apply_2
  jmp up_done_2

up_apply_2:
  mov temp r0
  xor0 open[2]
  mov open[2] r0
  mov r0 next[2]
  add0 temp
  mov next[2] r0
  mov r0 up[2]
  add0 temp
  mov up[2] r0

up_done_2:

  mov r0 frontier[3]
  jc r0 up_compute_3
  mov r0 frontier[2]
  jc r0 up_compute_3
  jmp up_done_3

up_compute_3:
  mov r0 frontier[3]
  muli0 65536
  mov temp r0
  mov r0 frontier[2]
  shri0 48
  add0 temp
  and0 open[3]
  jc r0 up_apply_3
  jmp up_done_3

up_apply_3:
  mov temp r0
  xor0 open[3]
  mov open[3] r0
  mov r0 next[3]
  add0 temp
  mov next[3] r0
  mov r0 up[3]
  add0 temp
  mov up[3] r0

up_done_3:

  ; Preferred move RIGHT: candidate cells are one column left.
  mov r0 frontier[0]
  jc r0 right_compute_0
  jmp right_done_0

right_compute_0:
  mov r0 frontier[0]
  shri0 1
  and0 open[0]
  jc r0 right_apply_0
  jmp right_done_0

right_apply_0:
  mov temp r0
  xor0 open[0]
  mov open[0] r0
  mov r0 next[0]
  add0 temp
  mov next[0] r0
  mov r0 right[0]
  add0 temp
  mov right[0] r0

right_done_0:

  mov r0 frontier[1]
  jc r0 right_compute_1
  jmp right_done_1

right_compute_1:
  mov r0 frontier[1]
  shri0 1
  and0 open[1]
  jc r0 right_apply_1
  jmp right_done_1

right_apply_1:
  mov temp r0
  xor0 open[1]
  mov open[1] r0
  mov r0 next[1]
  add0 temp
  mov next[1] r0
  mov r0 right[1]
  add0 temp
  mov right[1] r0

right_done_1:
  mov r0 frontier[2]
  jc r0 right_compute_2
  jmp right_done_2

right_compute_2:
  mov r0 frontier[2]
  shri0 1
  and0 open[2]
  jc r0 right_apply_2
  jmp right_done_2

right_apply_2:
  mov temp r0
  xor0 open[2]
  mov open[2] r0
  mov r0 next[2]
  add0 temp
  mov next[2] r0
  mov r0 right[2]
  add0 temp
  mov right[2] r0

right_done_2:
  mov r0 frontier[3]
  jc r0 right_compute_3
  jmp right_done_3

right_compute_3:
  mov r0 frontier[3]
  shri0 1
  and0 open[3]
  jc r0 right_apply_3
  jmp right_done_3

right_apply_3:
  mov temp r0
  xor0 open[3]
  mov open[3] r0
  mov r0 next[3]
  add0 temp
  mov next[3] r0
  mov r0 right[3]
  add0 temp
  mov right[3] r0

right_done_3:
  ; Preferred move DOWN: candidate cells are one row above the frontier.
  mov r0 frontier[0]
  jc r0 down_compute_0
  mov r0 frontier[1]
  jc r0 down_compute_0
  jmp down_done_0

down_compute_0:
  mov r0 frontier[0]
  shri0 16
  mov temp r0
  mov r0 frontier[1]
  andi0 65535
  muli0 281474976710656
  add0 temp
  and0 open[0]
  jc r0 down_apply_0
  jmp down_done_0

down_apply_0:
  mov temp r0
  xor0 open[0]
  mov open[0] r0
  mov r0 next[0]
  add0 temp
  mov next[0] r0
  mov r0 down[0]
  add0 temp
  mov down[0] r0

down_done_0:
  mov r0 frontier[1]
  jc r0 down_compute_1
  mov r0 frontier[2]
  jc r0 down_compute_1
  jmp down_done_1

down_compute_1:
  mov r0 frontier[1]
  shri0 16
  mov temp r0
  mov r0 frontier[2]
  andi0 65535
  muli0 281474976710656
  add0 temp
  and0 open[1]
  jc r0 down_apply_1
  jmp down_done_1

down_apply_1:
  mov temp r0
  xor0 open[1]
  mov open[1] r0
  mov r0 next[1]
  add0 temp
  mov next[1] r0
  mov r0 down[1]
  add0 temp
  mov down[1] r0

down_done_1:
  mov r0 frontier[2]
  jc r0 down_compute_2
  mov r0 frontier[3]
  jc r0 down_compute_2
  jmp down_done_2

down_compute_2:
  mov r0 frontier[2]
  shri0 16
  mov temp r0
  mov r0 frontier[3]
  andi0 65535
  muli0 281474976710656
  add0 temp
  and0 open[2]
  jc r0 down_apply_2
  jmp down_done_2

down_apply_2:
  mov temp r0
  xor0 open[2]
  mov open[2] r0
  mov r0 next[2]
  add0 temp
  mov next[2] r0
  mov r0 down[2]
  add0 temp
  mov down[2] r0

down_done_2:
  mov r0 frontier[3]
  jc r0 down_compute_3
  jmp down_done_3

down_compute_3:
  mov r0 frontier[3]
  shri0 16
  and0 open[3]
  jc r0 down_apply_3
  jmp down_done_3

down_apply_3:
  mov temp r0
  xor0 open[3]
  mov open[3] r0
  mov r0 next[3]
  add0 temp
  mov next[3] r0
  mov r0 down[3]
  add0 temp
  mov down[3] r0

down_done_3:
  ; Preferred move LEFT is implicit: candidate cells are one column right.
  mov r0 frontier[0]
  jc r0 left_compute_0
  jmp left_done_0

left_compute_0:
  mov r0 frontier[0]
  muli0 2
  and0 open[0]
  jc r0 left_apply_0
  jmp left_done_0

left_apply_0:
  mov temp r0
  xor0 open[0]
  mov open[0] r0
  mov r0 next[0]
  add0 temp
  mov next[0] r0

left_done_0:
  mov r0 frontier[1]
  jc r0 left_compute_1
  jmp left_done_1

left_compute_1:
  mov r0 frontier[1]
  muli0 2
  and0 open[1]
  jc r0 left_apply_1
  jmp left_done_1

left_apply_1:
  mov temp r0
  xor0 open[1]
  mov open[1] r0
  mov r0 next[1]
  add0 temp
  mov next[1] r0

left_done_1:
  mov r0 frontier[2]
  jc r0 left_compute_2
  jmp left_done_2

left_compute_2:
  mov r0 frontier[2]
  muli0 2
  and0 open[2]
  jc r0 left_apply_2
  jmp left_done_2

left_apply_2:
  mov temp r0
  xor0 open[2]
  mov open[2] r0
  mov r0 next[2]
  add0 temp
  mov next[2] r0

left_done_2:
  mov r0 frontier[3]
  jc r0 left_compute_3
  jmp left_done_3

left_compute_3:
  mov r0 frontier[3]
  muli0 2
  and0 open[3]
  jc r0 left_apply_3
  jmp left_done_3

left_apply_3:
  mov temp r0
  xor0 open[3]
  mov open[3] r0
  mov r0 next[3]
  add0 temp
  mov next[3] r0

left_done_3:
  mov frontier[0] next[0]
  mov frontier[1] next[1]
  mov frontier[2] next[2]
  mov frontier[3] next[3]
  mov r0 robot_chunk
  subi0 1
  jc r0 bfs_check_robot_high
  mov r0 robot_chunk
  jc r0 bfs_check_robot_1
  jmp bfs_check_robot_0

bfs_check_robot_high:
  mov r0 robot_chunk
  subi0 2
  jc r0 bfs_check_robot_3
  jmp bfs_check_robot_2

bfs_check_robot_3:
  mov r0 frontier[3]
  and0 robot_bit
  jc r0 path_ready
  jmp bfs_layer

bfs_check_robot_0:
  mov r0 frontier[0]
  and0 robot_bit
  jc r0 path_ready
  jmp bfs_layer

bfs_check_robot_1:
  mov r0 frontier[1]
  and0 robot_bit
  jc r0 path_ready
  jmp bfs_layer

bfs_check_robot_2:
  mov r0 frontier[2]
  and0 robot_bit
  jc r0 path_ready
  jmp bfs_layer

path_ready:
  imm next[0] 10

path_step:
  ; Test the three explicit direction masks for the robot's current bit.
  mov r0 robot_chunk
  subi0 1
  jc r0 path_chunk_high
  mov r0 robot_chunk
  jc r0 path_chunk_1
  jmp path_chunk_0

path_chunk_high:
  mov r0 robot_chunk
  subi0 2
  jc r0 path_chunk_3
  jmp path_chunk_2

path_chunk_3:
  mov r0 up[3]
  and0 robot_bit
  jc r0 move_up
  mov r0 right[3]
  and0 robot_bit
  jc r0 move_right
  mov r0 down[3]
  and0 robot_bit
  jc r0 move_down
  jmp move_left

path_chunk_0:
  mov r0 up[0]
  and0 robot_bit
  jc r0 move_up
  mov r0 right[0]
  and0 robot_bit
  jc r0 move_right
  mov r0 down[0]
  and0 robot_bit
  jc r0 move_down
  jmp move_left

path_chunk_1:
  mov r0 up[1]
  and0 robot_bit
  jc r0 move_up
  mov r0 right[1]
  and0 robot_bit
  jc r0 move_right
  mov r0 down[1]
  and0 robot_bit
  jc r0 move_down
  jmp move_left

path_chunk_2:
  mov r0 up[2]
  and0 robot_bit
  jc r0 move_up
  mov r0 right[2]
  and0 robot_bit
  jc r0 move_right
  mov r0 down[2]
  and0 robot_bit
  jc r0 move_down

move_left:
  mov temp robot_pos
  mov r0 robot_pos
  subi0 1
  mov robot_pos r0
  mov r0 robot_offset
  subi0 1
  mov robot_offset r0
  mov r0 robot_bit
  divi0 2
  mov robot_bit r0
  jmp move_draw

move_up:
  mov temp robot_pos
  mov r0 robot_pos
  subi0 16
  mov robot_pos r0
  mov r0 robot_offset
  subi0 15
  jc r0 move_up_same_chunk
  mov r0 robot_chunk
  subi0 1
  mov robot_chunk r0
  mov r0 robot_offset
  addi0 48
  mov robot_offset r0
  mov r0 robot_bit
  muli0 281474976710656
  mov robot_bit r0
  jmp move_draw

move_up_same_chunk:
  mov r0 robot_offset
  subi0 16
  mov robot_offset r0
  mov r0 robot_bit
  divi0 65536
  mov robot_bit r0
  jmp move_draw

move_right:
  mov temp robot_pos
  mov r0 robot_pos
  addi0 1
  mov robot_pos r0
  mov r0 robot_offset
  addi0 1
  mov robot_offset r0
  mov r0 robot_bit
  muli0 2
  mov robot_bit r0
  jmp move_draw

move_down:
  mov temp robot_pos
  mov r0 robot_pos
  addi0 16
  mov robot_pos r0
  mov r0 robot_offset
  subi0 47
  jc r0 move_down_next_chunk
  mov r0 robot_offset
  addi0 16
  mov robot_offset r0
  mov r0 robot_bit
  muli0 65536
  mov robot_bit r0
  jmp move_draw

move_down_next_chunk:
  mov r0 robot_chunk
  addi0 1
  mov robot_chunk r0
  mov r0 robot_offset
  subi0 48
  mov robot_offset r0
  mov r0 robot_bit
  divi0 281474976710656
  mov robot_bit r0

move_draw:
  screen_addr temp
  screen_data black
  screen_addr robot_pos
  screen_data next[0]
  screen_swap one
  jeqrs robot_pos flag_pos next_round
  jmp path_step
