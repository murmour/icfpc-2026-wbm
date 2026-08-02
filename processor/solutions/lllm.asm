.screen 16 16
; The storage ring holds two values per slot plus two control values, with
; tokens on alternating pipe cells: 2 * (2 * 22 + 2) = 92.
.memory 22 92
.kind lllm

; Setup and runtime aliases share slots once source packing has finished.
.reg width r2
.reg height r3
.reg one r3
.reg start_pos r4
.reg x r4
.reg row r5
.reg y r5
.reg rows_left r6
.reg dir r6
.reg cols_left r7
.reg a r7
.reg pack_count r8
.reg b r8
.reg mem_addr r9
.reg token r9
.reg cell_token r10
.reg ticks r10
.reg cell r11
.reg pos r11
.reg packed r12
.reg word r12
.reg factor r13
.reg word2 r13
.reg col r14
.reg prev r14

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

start:
  read width
  read height
  imm row 0
  mov rows_left height
  imm pack_count 0
  imm mem_addr 0
  imm packed 0
  imm factor 1

setup_row:
  mov cols_left width
  imm col 0

  mov r0 row
  muli0 16
  screen_addr r0

setup_cell:
  read cell

  ; Coordinate checks distinguish outer walls from the `-` instruction.
  jc row setup_not_top
  jmp setup_wall

setup_not_top:
  mov r0 rows_left
  subi0 1
  jc r0 setup_not_bottom
  jmp setup_wall

setup_not_bottom:
  jc col setup_not_left
  jmp setup_wall

setup_not_left:
  mov r0 cols_left
  subi0 1
  jc r0 setup_interior
  jmp setup_wall

setup_interior:
  ; Spaces dominate, so they take the shortest classification path.
  mov r0 cell
  subi0 32
  jc r0 setup_nonspace
  imm cell_token 0
  imm cell 0
  jmp setup_emit

setup_nonspace:
  mov r0 cell
  subi0 45
  jc r0 setup_digit_or_later
  mov r0 cell
  subi0 43
  jc r0 setup_minus

setup_plus:
  imm cell_token 16
  imm cell 10
  jmp setup_emit

setup_minus:
  imm cell_token 17
  imm cell 10
  jmp setup_emit

setup_digit_or_later:
  mov r0 cell
  subi0 57
  jc r0 setup_symbol
  mov r0 cell
  subi0 43
  mov cell_token r0
  imm cell 8
  jmp setup_emit

setup_symbol:
  mov r0 cell
  subi0 60
  jc r0 setup_after_left
  imm cell_token 4
  imm cell 3
  jmp setup_emit

setup_after_left:
  mov r0 cell
  subi0 62
  jc r0 setup_at_or_later
  imm cell_token 2
  imm cell 3
  jmp setup_emit

setup_at_or_later:
  mov r0 cell
  subi0 64
  jc r0 setup_after_at

  ; Store the start as one packed position. The @ token itself is empty.
  mov r0 row
  muli0 16
  add0 col
  mov start_pos r0
  imm cell_token 0
  imm cell 9
  jmp setup_emit

setup_after_at:
  mov r0 cell
  subi0 72
  jc r0 setup_after_h
  imm cell_token 19
  imm cell 3
  jmp setup_emit

setup_after_h:
  mov r0 cell
  subi0 77
  jc r0 setup_after_m
  imm cell_token 15
  imm cell 12
  jmp setup_emit

setup_after_m:
  mov r0 cell
  subi0 88
  jc r0 setup_after_x
  imm cell_token 18
  imm cell 3
  jmp setup_emit

setup_after_x:
  mov r0 cell
  subi0 94
  jc r0 setup_down
  imm cell_token 1
  imm cell 3
  jmp setup_emit

setup_down:
  imm cell_token 3
  imm cell 3
  jmp setup_emit

setup_wall:
  imm cell_token 20
  imm cell 4

setup_emit:
  screen_data cell

  mov r0 cell_token
  mul0 factor
  add0 packed
  mov packed r0

  mov r0 factor
  muli0 32
  mov factor r0

  inc col
  dec cols_left
  inc pack_count

  jeqs pack_count 12 setup_flush

setup_after_flush:
  jc cols_left setup_cell

setup_row_done:
  inc row
  dec rows_left
  jc rows_left setup_row

  ; A partial final group still needs to be written.
  jc pack_count setup_flush_final
  jmp source_stored

setup_flush_final:
  store mem_addr packed

source_stored:
  ; Fence the asynchronous stores, then decode the packed start position.
  imm pos 0
  load word pos

  mov r0 x
  divi0 16
  mov y r0
  mov r0 x
  andi0 15
  mov x r0

  imm one 1
  imm dir 1
  imm a 0
  imm b 0
  imm token 0
  screen_swap one
  jmp next_round

setup_flush:
  store mem_addr packed
  inc mem_addr
  imm packed 0
  imm factor 1
  imm pack_count 0
  jmp setup_after_flush

next_round:
  read ticks

  ; Save previous_position*32 + previous_token in one register.
  mov r0 y
  muli0 16
  add0 x
  muli0 32
  add0 token
  mov prev r0

tick_loop:
  jc ticks execute_tick
  jmp render_round

execute_tick:
  dec ticks
  jc token execute_nonspace
  jmp move_man

execute_nonspace:
  ; Tokens 1..4 set the direction directly.
  mov r0 token
  subi0 4
  jc r0 execute_after_direction
  mov r0 token
  subi0 1
  mov dir r0
  jmp move_man

execute_after_direction:
  ; Tokens 5..14 are literal digits.
  mov r0 token
  subi0 14
  jc r0 execute_symbol
  mov r0 token
  subi0 5
  mov a r0
  jmp move_man

execute_symbol:
  mov r0 token
  subi0 15
  jc r0 execute_after_m
  mov b a
  jmp move_man

execute_after_m:
  mov r0 token
  subi0 16
  jc r0 execute_after_plus
  mov r0 a
  add0 b
  mov a r0
  jmp move_man

execute_after_plus:
  mov r0 token
  subi0 17
  jc r0 execute_after_minus
  mov r0 a
  sub0 b
  mov a r0
  jmp move_man

execute_after_minus:
  mov r0 token
  subi0 18
  jc r0 execute_halt

  ; X turns clockwise for positive A and counterclockwise for negative A.
  jc a turn_clockwise
  mov r0 a

  ; Divide first to avoid the INT64_MIN negation edge case.
  divi0 2
  neg r0
  jc r0 turn_counterclockwise
  jmp move_man

turn_clockwise:
  inc dir
  mov r0 dir
  subi0 3
  jc r0 turn_wrap_zero
  jmp move_man

turn_wrap_zero:
  imm dir 0
  jmp move_man

turn_counterclockwise:
  jc dir turn_counter_nonzero
  imm dir 3
  jmp move_man

turn_counter_nonzero:
  dec dir
  jmp move_man

execute_halt:
  jmp render_halted

move_man:
  jc dir move_not_up
  dec y
  jmp fetch_token

move_not_up:
  mov r0 dir
  subi0 1
  jc r0 move_down_or_left
  inc x
  jmp fetch_token

move_down_or_left:
  mov r0 dir
  subi0 2
  jc r0 move_left
  inc y
  jmp fetch_token

move_left:
  dec x

fetch_token:
  ; linear position = y*width + x
  mov r0 y
  mul0 width
  add0 x
  mov pos r0

  ; address = floor(linear/12)
  divi0 12
  mov word r0
  load word2 word

  ; index = linear - address*12
  muli0 12
  mov word r0
  mov r0 pos
  sub0 word
  mov word r0

  ; Keep the evaluator-sensitive shift count below 32. Select one of the two
  ; 30-bit halves, then shift by 0, 5, 10, 15, 20, or 25.
  mov r0 word
  subi0 5
  jc r0 fetch_high_half
  mov pos word2
  jmp fetch_shift

fetch_high_half:
  mov r0 word2
  divi0 1073741824
  mov pos r0
  mov r0 word
  subi0 6
  mov word r0

fetch_shift:
  mov r0 word
  muli0 5
  mov word r0
  mov r0 pos
  shr0 word
  andi0 31
  mov token r0

  ; The only token above H is a room wall.
  subi0 19
  jc r0 render_halted
  jmp tick_loop

render_round:
  imm ticks 1
  jmp render_common

render_halted:
  imm ticks -1

render_common:
  ; Restore the instruction beneath the previous committed red pixel.
  mov r0 prev
  andi0 31
  mov pos r0

  ; Convert the previous token to its static color.
  imm word 0
  jc pos restore_nonspace
  jmp restore_ready

restore_nonspace:
  mov r0 pos
  subi0 4
  jc r0 restore_after_direction
  imm word 3
  jmp restore_ready

restore_after_direction:
  mov r0 pos
  subi0 14
  jc r0 restore_after_digit
  imm word 8
  jmp restore_ready

restore_after_digit:
  mov r0 pos
  subi0 15
  jc r0 restore_after_m
  imm word 12
  jmp restore_ready

restore_after_m:
  mov r0 pos
  subi0 17
  jc r0 restore_after_arithmetic
  imm word 10
  jmp restore_ready

restore_after_arithmetic:
  mov r0 pos
  subi0 19
  jc r0 restore_wall
  imm word 3
  jmp restore_ready

restore_wall:
  imm word 4

restore_ready:
  mov r0 prev
  divi0 32
  screen_addr r0
  screen_data word

  mov r0 y
  muli0 16
  add0 x
  screen_addr r0
  imm r0 9
  screen_data r0
  screen_swap one

  ; A negative `ticks` value marks H or a wall collision.
  jc ticks next_round

halt:
  jmp halt
