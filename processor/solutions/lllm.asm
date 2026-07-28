.screen 16 16
; The storage ring holds two values per slot plus two control values, with
; tokens on alternating pipe cells: 2 * (2 * 22 + 2) = 92.
.memory 22 92
.kind lllm

; Interpret a 16x16-or-smaller LLLM room.
;
; The source is converted to five-bit tokens and packed continuously, twelve
; cells per word. Twenty-two words cover the largest 16x16 source.
;
; Tokens:
;   0      space / the vacated @ cell
;   1..4   up, right, down, left
;   5..14  digits 0..9
;   15     M
;   16,17  +,-
;   18,19  X,H
;   20     wall
;
; Registers:
;   r0,r1   ALU and immediate scratch
;   r2,r3   setup width/height; width / constant one at runtime
;   r4,r5   packed start / setup y; runtime x, y
;   r6..r10 setup counters; runtime direction, A, B, token, ticks
;   r11     input character / runtime linear position or color
;   r12     packed-word accumulator / loaded packed word
;   r13     packing factor / loaded packed word
;   r14     setup x / packed previous display state

start:
  read r2
  read r3
  imm r5 0
  mov r6 r3
  imm r8 0
  imm r9 0
  imm r12 0
  imm r13 1

setup_row:
  mov r7 r2
  imm r14 0

  mov r0 r5
  muli0 16
  screen_addr r0

setup_cell:
  read r11

  ; Coordinate checks distinguish outer walls from the `-` instruction.
  jc r5 setup_not_top
  jmp setup_wall
setup_not_top:
  mov r0 r6
  subi0 1
  jc r0 setup_not_bottom
  jmp setup_wall
setup_not_bottom:
  jc r14 setup_not_left
  jmp setup_wall
setup_not_left:
  mov r0 r7
  subi0 1
  jc r0 setup_interior
  jmp setup_wall

setup_interior:
  ; Spaces dominate, so they take the shortest classification path.
  mov r0 r11
  subi0 32
  jc r0 setup_nonspace
  imm r10 0
  imm r11 0
  jmp setup_emit

setup_nonspace:
  mov r0 r11
  subi0 45
  jc r0 setup_digit_or_later
  mov r0 r11
  subi0 43
  jc r0 setup_minus
setup_plus:
  imm r10 16
  imm r11 10
  jmp setup_emit
setup_minus:
  imm r10 17
  imm r11 10
  jmp setup_emit

setup_digit_or_later:
  mov r0 r11
  subi0 57
  jc r0 setup_symbol
  mov r0 r11
  subi0 43
  mov r10 r0
  imm r11 8
  jmp setup_emit

setup_symbol:
  mov r0 r11
  subi0 60
  jc r0 setup_after_left
  imm r10 4
  imm r11 3
  jmp setup_emit
setup_after_left:
  mov r0 r11
  subi0 62
  jc r0 setup_at_or_later
  imm r10 2
  imm r11 3
  jmp setup_emit

setup_at_or_later:
  mov r0 r11
  subi0 64
  jc r0 setup_after_at
  ; Store the start as one packed position. The @ token itself is empty.
  mov r0 r5
  muli0 16
  add0 r14
  mov r4 r0
  imm r10 0
  imm r11 9
  jmp setup_emit
setup_after_at:
  mov r0 r11
  subi0 72
  jc r0 setup_after_h
  imm r10 19
  imm r11 3
  jmp setup_emit
setup_after_h:
  mov r0 r11
  subi0 77
  jc r0 setup_after_m
  imm r10 15
  imm r11 12
  jmp setup_emit
setup_after_m:
  mov r0 r11
  subi0 88
  jc r0 setup_after_x
  imm r10 18
  imm r11 3
  jmp setup_emit
setup_after_x:
  mov r0 r11
  subi0 94
  jc r0 setup_down
  imm r10 1
  imm r11 3
  jmp setup_emit
setup_down:
  imm r10 3
  imm r11 3
  jmp setup_emit

setup_wall:
  imm r10 20
  imm r11 4

setup_emit:
  screen_data r11

  mov r0 r10
  mul0 r13
  add0 r12
  mov r12 r0

  mov r0 r13
  muli0 32
  mov r13 r0

  inc r14
  dec r7
  inc r8

  jeqs r8 12 setup_flush
setup_after_flush:
  jc r7 setup_cell

setup_row_done:
  inc r5
  dec r6
  jc r6 setup_row

  ; A partial final group still needs to be written.
  jc r8 setup_flush_final
  jmp source_stored

setup_flush_final:
  store r9 r12

source_stored:
  ; Fence the asynchronous stores, then decode the packed start position.
  imm r11 0
  load r12 r11

  mov r0 r4
  divi0 16
  mov r5 r0
  mov r0 r4
  andi0 15
  mov r4 r0

  imm r3 1
  imm r6 1
  imm r7 0
  imm r8 0
  imm r9 0
  screen_swap r3
  jmp next_round

setup_flush:
  store r9 r12
  inc r9
  imm r12 0
  imm r13 1
  imm r8 0
  jmp setup_after_flush

next_round:
  read r10

  ; Save previous_position*32 + previous_token in one register.
  mov r0 r5
  muli0 16
  add0 r4
  muli0 32
  add0 r9
  mov r14 r0

tick_loop:
  jc r10 execute_tick
  jmp render_round

execute_tick:
  dec r10
  jc r9 execute_nonspace
  jmp move_man

execute_nonspace:
  ; Tokens 1..4 set the direction directly.
  mov r0 r9
  subi0 4
  jc r0 execute_after_direction
  mov r0 r9
  subi0 1
  mov r6 r0
  jmp move_man

execute_after_direction:
  ; Tokens 5..14 are literal digits.
  mov r0 r9
  subi0 14
  jc r0 execute_symbol
  mov r0 r9
  subi0 5
  mov r7 r0
  jmp move_man

execute_symbol:
  mov r0 r9
  subi0 15
  jc r0 execute_after_m
  mov r8 r7
  jmp move_man

execute_after_m:
  mov r0 r9
  subi0 16
  jc r0 execute_after_plus
  mov r0 r7
  add0 r8
  mov r7 r0
  jmp move_man

execute_after_plus:
  mov r0 r9
  subi0 17
  jc r0 execute_after_minus
  mov r0 r7
  sub0 r8
  mov r7 r0
  jmp move_man

execute_after_minus:
  mov r0 r9
  subi0 18
  jc r0 execute_halt

  ; X turns clockwise for positive A and counterclockwise for negative A.
  jc r7 turn_clockwise
  mov r0 r7
  ; Divide first to avoid the INT64_MIN negation edge case.
  divi0 2
  neg r0
  jc r0 turn_counterclockwise
  jmp move_man

turn_clockwise:
  inc r6
  mov r0 r6
  subi0 3
  jc r0 turn_wrap_zero
  jmp move_man
turn_wrap_zero:
  imm r6 0
  jmp move_man

turn_counterclockwise:
  jc r6 turn_counter_nonzero
  imm r6 3
  jmp move_man
turn_counter_nonzero:
  dec r6
  jmp move_man

execute_halt:
  jmp render_halted

move_man:
  jc r6 move_not_up
  dec r5
  jmp fetch_token
move_not_up:
  mov r0 r6
  subi0 1
  jc r0 move_down_or_left
  inc r4
  jmp fetch_token
move_down_or_left:
  mov r0 r6
  subi0 2
  jc r0 move_left
  inc r5
  jmp fetch_token
move_left:
  dec r4

fetch_token:
  ; linear position = y*width + x
  mov r0 r5
  mul0 r2
  add0 r4
  mov r11 r0

  ; address = floor(linear/12)
  divi0 12
  mov r12 r0
  load r13 r12

  ; index = linear - address*12
  muli0 12
  mov r12 r0
  mov r0 r11
  sub0 r12
  mov r12 r0

  ; Keep the evaluator-sensitive shift count below 32. Select one of the two
  ; 30-bit halves, then shift by 0, 5, 10, 15, 20, or 25.
  mov r0 r12
  subi0 5
  jc r0 fetch_high_half
  mov r11 r13
  jmp fetch_shift

fetch_high_half:
  mov r0 r13
  divi0 1073741824
  mov r11 r0
  mov r0 r12
  subi0 6
  mov r12 r0

fetch_shift:
  mov r0 r12
  muli0 5
  mov r12 r0
  mov r0 r11
  shr0 r12
  andi0 31
  mov r9 r0

  ; The only token above H is a room wall.
  subi0 19
  jc r0 render_halted
  jmp tick_loop

render_round:
  imm r10 1
  jmp render_common

render_halted:
  imm r10 -1

render_common:
  ; Restore the instruction beneath the previous committed red pixel.
  mov r0 r14
  andi0 31
  mov r11 r0

  ; Convert the previous token to its static color.
  imm r12 0
  jc r11 restore_nonspace
  jmp restore_ready
restore_nonspace:
  mov r0 r11
  subi0 4
  jc r0 restore_after_direction
  imm r12 3
  jmp restore_ready
restore_after_direction:
  mov r0 r11
  subi0 14
  jc r0 restore_after_digit
  imm r12 8
  jmp restore_ready
restore_after_digit:
  mov r0 r11
  subi0 15
  jc r0 restore_after_m
  imm r12 12
  jmp restore_ready
restore_after_m:
  mov r0 r11
  subi0 17
  jc r0 restore_after_arithmetic
  imm r12 10
  jmp restore_ready
restore_after_arithmetic:
  mov r0 r11
  subi0 19
  jc r0 restore_wall
  imm r12 3
  jmp restore_ready
restore_wall:
  imm r12 4

restore_ready:
  mov r0 r14
  divi0 32
  screen_addr r0
  screen_data r12

  mov r0 r5
  muli0 16
  add0 r4
  screen_addr r0
  imm r0 9
  screen_data r0
  screen_swap r3

  ; A negative r10 marks H or a wall collision.
  jc r10 next_round
halt:
  jmp halt
