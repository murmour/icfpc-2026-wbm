.screen 16 16
; Bulk source loading fills the storage ring before the fence read. Preserve
; two values per slot plus two control values on alternating pipe cells.
.memory 32 132
.kind llm

; Interpret an LLM program containing up to three rooms and two pipes.
;
; Source memory:
;   0..31  eight row-major ASCII cells packed in base 256
;
; Persistent man state:
;             x   y  dir   A   B  halted  left right top bottom previous
;   man 0:   20  21   22  23  24    25     26   27   28   29     30
;   man 1:   31  32   33  34  35    36     37   38   39   40     41
;   man 2:   42  43   44  45  46    47     48   49   50   51     52

start:
  read r2
  read r3
  mul r4 r2 r3

  imm r5 0
  imm r6 0
  imm r7 0
  imm r8 1
  mov r0 r8
  imm r9 0
  imm r11 0
  imm r12 0
  imm r13 0
  imm r18 1

  ; Missing man slots are permanently halted.
  imm r25 1
  imm r36 1
  imm r47 1

read_source:
  read r10

  ; Record each @ in row-major room order.
  subi r14 r10 64
  jc r14 read_not_at
  subi r14 r10 63
  jc r14 read_at
  jmp read_not_at

read_at:
  jeqs r13 0 read_at_man0
  jeqs r13 1 read_at_man1

read_at_man2:
  mov r42 r11
  mov r43 r12
  imm r44 1
  imm r45 0
  imm r46 0
  imm r47 0
  inc r13
  jmp read_not_at

read_at_man0:
  mov r20 r11
  mov r21 r12
  imm r22 1
  imm r23 0
  imm r24 0
  imm r25 0
  inc r13
  jmp read_not_at

read_at_man1:
  mov r31 r11
  mov r32 r12
  imm r33 1
  imm r34 0
  imm r35 0
  imm r36 0
  inc r13

read_not_at:
  ; Paint a provisional cell while the source is already in hand. Room
  ; horizontals and all pipe cells are corrected after topology parsing.
  imm r17 3
  jeqs r10 32 read_color_black
  jeqs r10 64 read_color_man
  jeqs r10 124 read_color_wall
  jeqs r10 43 read_color_arithmetic
  jeqs r10 45 read_color_arithmetic
  jeqs r10 77 read_color_blue
  jeqs r10 114 read_color_pipe_instruction
  jeqs r10 115 read_color_pipe_instruction
  subi r14 r10 47
  jc r14 read_color_digit_high
  jmp read_color_ready

read_color_digit_high:
  subi r14 r10 57
  jc r14 read_color_ready
  imm r17 8
  jmp read_color_ready

read_color_black:
  imm r17 0
  jmp read_color_ready

read_color_man:
  imm r17 9
  jmp read_color_ready

read_color_wall:
  imm r17 4
  jmp read_color_ready

read_color_arithmetic:
  imm r17 10
  jmp read_color_ready

read_color_blue:
  imm r17 12
  jmp read_color_ready

read_color_pipe_instruction:
  imm r17 13

read_color_ready:
  screen_data r17

  mov r0 r10
  mul0 r8
  add0 r7
  mov r7 r0
  muli r8 r8 256
  inc r9
  inc r5
  inc r11

read_after_position:

  jeqs r9 8 read_flush

read_after_flush:
  jeqrs r5 r4 read_source_done
  jeqrs r11 r2 read_next_row
  jmp read_source

read_next_row:
  imm r11 0
  inc r12
  muli r16 r12 16
  screen_addr r16
  jmp read_source

read_flush:
  store r6 r7
  inc r6
  imm r7 0
  imm r8 1
  mov r0 r8
  imm r9 0
  jmp read_after_flush

read_source_done:
  jc r9 read_flush_final
  jmp source_stored

read_flush_final:
  store r6 r7

source_stored:
  ; A blocking read fences the asynchronous source stores.
  imm r6 0
  load r10 r6

  ; Find each room's bounds from its @. A row scan reaches | walls;
  ; scanning the left wall vertically reaches + corners.
  imm r53 0

find_room:
  jeqs r53 0 find_room_load0
  jeqs r53 1 find_room_load1

find_room_load2:
  mov r54 r42
  mov r55 r43
  jmp find_left_start

find_room_load0:
  mov r54 r20
  mov r55 r21
  jmp find_left_start

find_room_load1:
  mov r54 r31
  mov r55 r32

find_left_start:
  mov r56 r54

find_left:
  dec r56
  mov r0 r55
  mul0 r2
  add0 r56
  mov r60 r0
  load8 r61 r60 r62 r63 r64 r65
  jeqs r61 124 find_right_start
  jmp find_left

find_right_start:
  mov r57 r54

find_right:
  inc r57
  mov r0 r55
  mul0 r2
  add0 r57
  mov r60 r0
  load8 r61 r60 r62 r63 r64 r65
  jeqs r61 124 find_top_start
  jmp find_right

find_top_start:
  mov r58 r55

find_top:
  dec r58
  mov r0 r58
  mul0 r2
  add0 r56
  mov r60 r0
  load8 r61 r60 r62 r63 r64 r65
  jeqs r61 43 find_bottom_start
  jmp find_top

find_bottom_start:
  mov r59 r55

find_bottom:
  inc r59
  mov r0 r59
  mul0 r2
  add0 r56
  mov r60 r0
  load8 r61 r60 r62 r63 r64 r65
  jeqs r61 43 find_room_save
  jmp find_bottom

find_room_save:
  jeqs r53 0 find_room_save0
  jeqs r53 1 find_room_save1

find_room_save2:
  mov r48 r56
  mov r49 r57
  mov r50 r58
  mov r51 r59
  jmp find_room_next

find_room_save0:
  mov r26 r56
  mov r27 r57
  mov r28 r58
  mov r29 r59
  jmp find_room_next

find_room_save1:
  mov r37 r56
  mov r38 r57
  mov r39 r58
  mov r40 r59

find_room_next:
  ; The streaming renderer treats '-' and '+' as instructions. Correct the
  ; two horizontal walls now that this room's bounds are known.
  imm r17 4
  mov r0 r58
  muli0 16
  add0 r56
  mov r16 r0
  screen_addr r16
  mov r0 r57
  sub0 r56
  addi0 1
  mov r60 r0

find_room_draw_top:
  screen_data r17
  dec r60
  jc r60 find_room_draw_top

  mov r0 r59
  muli0 16
  add0 r56
  mov r16 r0
  screen_addr r16
  mov r0 r57
  sub0 r56
  addi0 1
  mov r60 r0

find_room_draw_bottom:
  screen_data r17
  dec r60
  jc r60 find_room_draw_bottom

  inc r53
  jeqrs r53 r13 render_initial_start
  jmp find_room

render_initial_start:
  jmp parse_pipes_start

; Pipe metadata:
;             len src dst first last path0 path1 path2 occupancy plane0
;   pipe 0:    67  68  69   70    71    72    73    74      75       76
;   pipe 1:    77  78  79   80    81    82    83    84      85       86
;
; The remaining value bitplanes are r4..r7 for pipe 0 and
; r9,r11,r12,r16 for pipe 1. Destination masks are r8 and r53.
; r87 is the pipe count.

parse_pipes_start:
  ; Force both paths to be painted on the initial frame.
  imm r54 -1
  imm r55 -1
  imm r67 0
  imm r68 -1
  imm r69 -1
  imm r77 0
  imm r78 -1
  imm r79 -1
  imm r87 0
  imm r88 0

pipe_scan_room:
  jeqs r88 0 pipe_scan_room0
  jeqs r88 1 pipe_scan_room1

pipe_scan_room2:
  mov r52 r48
  mov r56 r49
  mov r57 r50
  mov r17 r51
  jmp pipe_scan_top_start

pipe_scan_room0:
  mov r52 r26
  mov r56 r27
  mov r57 r28
  mov r17 r29
  jmp pipe_scan_top_start

pipe_scan_room1:
  mov r52 r37
  mov r56 r38
  mov r57 r39
  mov r17 r40

pipe_scan_top_start:
  imm r55 0
  jc r57 pipe_scan_top_setup
  jmp pipe_scan_right_start

pipe_scan_top_setup:
  mov r90 r52
  addi r91 r57 -1

pipe_scan_top:
  mov r0 r91
  mul0 r2
  add0 r90
  mov r89 r0
  load8 r10 r89 r62 r63 r64 r65
  jeqs r10 94 pipe_candidate_up

pipe_scan_top_next:
  inc r90
  sub r14 r90 r56
  jc r14 pipe_scan_right_start
  jmp pipe_scan_top

pipe_candidate_up:
  imm r93 0
  jmp pipe_trace_start

pipe_scan_right_start:
  imm r55 1
  addi r90 r56 1
  jeqrs r90 r2 pipe_scan_bottom_start
  mov r91 r57

pipe_scan_right:
  mov r0 r91
  mul0 r2
  add0 r90
  mov r89 r0
  load8 r10 r89 r62 r63 r64 r65
  jeqs r10 62 pipe_candidate_right

pipe_scan_right_next:
  inc r91
  sub r14 r91 r17
  jc r14 pipe_scan_bottom_start
  jmp pipe_scan_right

pipe_candidate_right:
  imm r93 1
  jmp pipe_trace_start

pipe_scan_bottom_start:
  imm r55 2
  addi r91 r17 1
  jeqrs r91 r3 pipe_scan_left_start
  mov r90 r52

pipe_scan_bottom:
  mov r0 r91
  mul0 r2
  add0 r90
  mov r89 r0
  load8 r10 r89 r62 r63 r64 r65
  jeqs r10 118 pipe_candidate_down

pipe_scan_bottom_next:
  inc r90
  sub r14 r90 r56
  jc r14 pipe_scan_left_start
  jmp pipe_scan_bottom

pipe_candidate_down:
  imm r93 2
  jmp pipe_trace_start

pipe_scan_left_start:
  imm r55 3
  jc r52 pipe_scan_left_setup
  jmp pipe_scan_room_done

pipe_scan_left_setup:
  addi r90 r52 -1
  mov r91 r57

pipe_scan_left:
  mov r0 r91
  mul0 r2
  add0 r90
  mov r89 r0
  load8 r10 r89 r62 r63 r64 r65
  jeqs r10 60 pipe_candidate_left

pipe_scan_left_next:
  inc r91
  sub r14 r91 r17
  jc r14 pipe_scan_room_done
  jmp pipe_scan_left

pipe_candidate_left:
  imm r93 3

pipe_trace_start:
  mov r58 r90
  mov r59 r91

  ; Keep the source room and first arrowhead.
  mov r94 r88
  mov r0 r91
  muli0 16
  add0 r90
  mov r9 r0
  imm r11 0
  imm r12 0
  imm r16 0
  imm r30 0
  imm r19 1
  mov r0 r19
  imm r92 0
  imm r54 0
  imm r88 0
  imm r15 1

pipe_trace_append:
  mov r0 r91
  muli0 16
  add0 r90
  mov r62 r0
  mul0 r19
  add0 r30
  mov r30 r0
  muli r19 r19 256
  inc r92
  inc r54
  muli r15 r15 2
  jeqs r54 21 pipe_trace_overflow
  jeqs r92 7 pipe_trace_flush

pipe_trace_after_flush:

  jeqs r93 0 pipe_trace_move_up
  jeqs r93 1 pipe_trace_move_right
  jeqs r93 2 pipe_trace_move_down

pipe_trace_move_left:
  addi r61 r90 -1
  mov r60 r91
  jmp pipe_trace_moved

pipe_trace_move_up:
  mov r61 r90
  addi r60 r91 -1
  jmp pipe_trace_moved

pipe_trace_move_right:
  addi r61 r90 1
  mov r60 r91
  jmp pipe_trace_moved

pipe_trace_move_down:
  mov r61 r90
  addi r60 r91 1

pipe_trace_moved:
  ; A point inside any room is necessarily the destination border.
  sub r14 r26 r61
  jc r14 pipe_trace_check_room1
  sub r14 r61 r27
  jc r14 pipe_trace_check_room1
  sub r14 r28 r60
  jc r14 pipe_trace_check_room1
  sub r14 r60 r29
  jc r14 pipe_trace_check_room1
  imm r66 0
  jmp pipe_trace_done

pipe_trace_check_room1:
  subi r14 r13 1
  jc r14 pipe_trace_check_room1_body
  jmp pipe_trace_check_room2

pipe_trace_check_room1_body:
  sub r14 r37 r61
  jc r14 pipe_trace_check_room2
  sub r14 r61 r38
  jc r14 pipe_trace_check_room2
  sub r14 r39 r60
  jc r14 pipe_trace_check_room2
  sub r14 r60 r40
  jc r14 pipe_trace_check_room2
  imm r66 1
  jmp pipe_trace_done

pipe_trace_check_room2:
  subi r14 r13 2
  jc r14 pipe_trace_check_room2_body
  jmp pipe_trace_continue

pipe_trace_check_room2_body:
  sub r14 r48 r61
  jc r14 pipe_trace_continue
  sub r14 r61 r49
  jc r14 pipe_trace_continue
  sub r14 r50 r60
  jc r14 pipe_trace_continue
  sub r14 r60 r51
  jc r14 pipe_trace_continue
  imm r66 2
  jmp pipe_trace_done

pipe_trace_continue:
  mov r90 r61
  mov r91 r60
  mov r14 r90
  neg r14
  jc r14 pipe_trace_overflow
  mov r14 r91
  neg r14
  jc r14 pipe_trace_overflow
  jeqrs r90 r2 pipe_trace_overflow
  sub r14 r90 r2
  jc r14 pipe_trace_overflow
  jeqrs r91 r3 pipe_trace_overflow
  sub r14 r91 r3
  jc r14 pipe_trace_overflow
  mov r0 r91
  mul0 r2
  add0 r90
  mov r89 r0
  load8 r10 r89 r62 r63 r64 r65
  jeqs r10 94 pipe_trace_set_up
  jeqs r10 62 pipe_trace_set_right
  jeqs r10 118 pipe_trace_set_down
  jeqs r10 60 pipe_trace_set_left
  jmp pipe_trace_append

pipe_trace_set_up:
  imm r93 0
  jmp pipe_trace_append

pipe_trace_set_right:
  imm r93 1
  jmp pipe_trace_append

pipe_trace_set_down:
  imm r93 2
  jmp pipe_trace_append

pipe_trace_set_left:
  imm r93 3
  jmp pipe_trace_append

pipe_trace_overflow:
  imm r66 9
  jmp pipe_trace_done

pipe_trace_flush:
  jeqs r88 0 pipe_trace_flush0
  jeqs r88 1 pipe_trace_flush1

pipe_trace_flush2:
  mov r16 r30
  jmp pipe_trace_flush_reset

pipe_trace_flush0:
  mov r11 r30
  jmp pipe_trace_flush_reset

pipe_trace_flush1:
  mov r12 r30

pipe_trace_flush_reset:
  inc r88
  imm r30 0
  imm r19 1
  mov r0 r19
  imm r92 0
  jmp pipe_trace_after_flush

pipe_trace_done:
  divi r15 r15 2

  ; Save a partial final path chunk.
  jc r92 pipe_trace_flush_final
  jmp pipe_trace_save

pipe_trace_flush_final:
  jeqs r88 0 pipe_trace_flush_final0
  jeqs r88 1 pipe_trace_flush_final1
  mov r16 r30
  jmp pipe_trace_save

pipe_trace_flush_final0:
  mov r11 r30
  jmp pipe_trace_save

pipe_trace_flush_final1:
  mov r12 r30

pipe_trace_save:
  mov r0 r91
  muli0 16
  add0 r90
  mov r63 r0

  ; A bend beside another room can look like a second source. Such a ghost
  ; traces the same suffix and terminal cell as its parent. Keep the longest
  ; candidate for each terminal cell, matching the canonical pipe parser.
  imm r92 1
  jc r87 pipe_trace_compare0
  jmp pipe_trace_save0

pipe_trace_compare0:
  jeqrs r63 r71 pipe_trace_same0
  subi r14 r87 1
  jc r14 pipe_trace_compare1
  jmp pipe_trace_save1

pipe_trace_same0:
  sub r14 r54 r67
  jc r14 pipe_trace_replace0
  jmp pipe_scan_resume

pipe_trace_replace0:
  imm r92 0
  jmp pipe_trace_save0

pipe_trace_compare1:
  jeqrs r63 r81 pipe_trace_same1
  jmp pipe_scan_resume

pipe_trace_same1:
  sub r14 r54 r77
  jc r14 pipe_trace_replace1
  jmp pipe_scan_resume

pipe_trace_replace1:
  imm r92 0
  jmp pipe_trace_save1

pipe_trace_save0:
  mov r67 r54
  mov r68 r94
  mov r69 r66
  mov r70 r9
  mov r71 r63
  mov r72 r11
  mov r73 r12
  mov r74 r16
  imm r75 0
  imm r76 0
  imm r4 0
  imm r5 0
  imm r6 0
  imm r7 0
  mov r8 r15
  jc r92 pipe_trace_increment_count
  jmp pipe_scan_resume

pipe_trace_save1:
  mov r77 r54
  mov r78 r94
  mov r79 r66
  mov r80 r9
  mov r81 r63
  mov r82 r11
  mov r83 r12
  mov r84 r16
  imm r85 0
  imm r86 0
  imm r9 0
  imm r11 0
  imm r12 0
  imm r16 0
  mov r53 r15
  jc r92 pipe_trace_increment_count
  jmp pipe_scan_resume

pipe_trace_increment_count:
  inc r87

pipe_scan_resume:
  mov r88 r94
  mov r90 r58
  mov r91 r59
  jeqs r55 0 pipe_scan_top_next
  jeqs r55 1 pipe_scan_right_next
  jeqs r55 2 pipe_scan_bottom_next
  jmp pipe_scan_left_next

pipe_scan_room_done:
  inc r88
  jeqrs r88 r13 topology_ready
  jmp pipe_scan_room

topology_ready:
  ; These two runtime flags reuse dirty topology slots and otherwise relied
  ; on power-on zero. Every other reused temporary is assigned before use.
  imm r64 0
  imm r19 0
  imm r54 -1
  imm r55 -1
  jmp render_pipes_start

next_round:
  read r19

  ; Clear the old man pixels before executing. This frees the three previous
  ; position slots for runtime scratch throughout the tick loop.
  imm r66 0

render_restore_man:
  jeqs r66 0 render_restore_load0
  jeqs r66 1 render_restore_load1

render_restore_load2:
  mov r0 r43
  muli0 16
  add0 r42
  mov r54 r0
  mov r94 r48
  mov r30 r49
  mov r41 r50
  mov r52 r51
  jmp render_restore_loaded

render_restore_load0:
  mov r0 r21
  muli0 16
  add0 r20
  mov r54 r0
  mov r94 r26
  mov r30 r27
  mov r41 r28
  mov r52 r29
  jmp render_restore_loaded

render_restore_load1:
  mov r0 r32
  muli0 16
  add0 r31
  mov r54 r0
  mov r94 r37
  mov r30 r38
  mov r41 r39
  mov r52 r40

render_restore_loaded:
  divi r89 r54 16
  mov r0 r54
  andi0 15
  mov r88 r0
  jeqrs r88 r94 render_restore_wall
  jeqrs r88 r30 render_restore_wall
  jeqrs r89 r41 render_restore_wall
  jeqrs r89 r52 render_restore_wall
  mov r0 r89
  mul0 r2
  add0 r88
  mov r14 r0
  load8 r10 r14 r62 r63 r64 r65
  jeqs r10 32 render_restore_black
  jeqs r10 64 render_restore_black
  jeqs r10 43 render_restore_arithmetic
  jeqs r10 45 render_restore_arithmetic
  subi r14 r10 47
  jc r14 render_restore_digit_or_symbol
  jmp render_restore_yellow

render_restore_digit_or_symbol:
  subi r14 r10 57
  jc r14 render_restore_symbol
  imm r17 8
  jmp render_restore_emit

render_restore_symbol:
  jeqs r10 77 render_restore_blue
  jeqs r10 114 render_restore_pipe_instruction
  jeqs r10 115 render_restore_pipe_instruction

render_restore_yellow:
  imm r17 3
  jmp render_restore_emit

render_restore_arithmetic:
  imm r17 10
  jmp render_restore_emit

render_restore_blue:
  imm r17 12
  jmp render_restore_emit

render_restore_pipe_instruction:
  imm r17 13
  jmp render_restore_emit

render_restore_wall:
  imm r17 4
  jmp render_restore_emit

render_restore_black:
  imm r17 0

render_restore_emit:
  screen_addr r54
  screen_data r17
  inc r66
  jeqrs r66 r13 tick_loop
  jmp render_restore_man

tick_loop:
  jc r19 execute_tick
  jmp render_pipes_start

execute_tick:
  imm r88 0

shift_pipe:
  jc r88 shift_pipe_load1

shift_pipe_load0:
  mov r89 r67
  mov r90 r75
  mov r91 r76
  mov r92 r4
  mov r93 r5
  mov r94 r6
  mov r30 r7
  mov r41 r8
  jmp shift_pipe_loaded

shift_pipe_load1:
  mov r89 r77
  mov r90 r85
  mov r91 r86
  mov r92 r9
  mov r93 r11
  mov r94 r12
  mov r30 r16
  mov r41 r53

shift_pipe_loaded:
  jc r89 shift_pipe_begin
  imm r62 1
  imm r63 0
  jmp shift_pipe_save

shift_pipe_begin:
  jc r90 shift_pipe_nonempty
  imm r62 0
  imm r63 0
  jmp shift_pipe_save

shift_pipe_nonempty:
  ; Pipes update destination-to-source. An empty destination lets every token
  ; advance. Otherwise, find the highest gap: every token below it advances,
  ; while the packed suffix above it remains in place.
  mov r0 r41
  muli0 2
  subi0 1
  mov r14 r0
  sub r10 r14 r90
  and r52 r10 r41
  jc r52 shift_pipe_move_all
  jc r10 shift_pipe_find_gap
  jmp shift_pipe_decode

shift_pipe_find_gap:
  ; Normalize the highest nonzero nibble of the empty-cell mask.
  subi r52 r10 255
  jc r52 shift_pipe_gap_above8
  subi r52 r10 15
  jc r52 shift_pipe_gap4

shift_pipe_gap0:
  mov r52 r10
  imm r14 1
  jmp shift_pipe_gap_nibble

shift_pipe_gap4:
  divi r52 r10 16
  imm r14 16
  jmp shift_pipe_gap_nibble

shift_pipe_gap_above8:
  subi r52 r10 4095
  jc r52 shift_pipe_gap_above12

shift_pipe_gap8:
  divi r52 r10 256
  imm r14 256
  jmp shift_pipe_gap_nibble

shift_pipe_gap_above12:
  subi r52 r10 65535
  jc r52 shift_pipe_gap16

shift_pipe_gap12:
  divi r52 r10 4096
  imm r14 4096
  jmp shift_pipe_gap_nibble

shift_pipe_gap16:
  divi r52 r10 65536
  imm r14 65536

shift_pipe_gap_nibble:
  ; Highest power of two in the four-bit value r52.
  mov r0 r52
  subi0 7
  jc r0 shift_pipe_gap_power8
  mov r0 r52
  subi0 3
  jc r0 shift_pipe_gap_power4
  mov r0 r52
  subi0 1
  jc r0 shift_pipe_gap_power2
  imm r0 1
  jmp shift_pipe_gap_power_ready

shift_pipe_gap_power2:
  imm r0 2
  jmp shift_pipe_gap_power_ready

shift_pipe_gap_power4:
  imm r0 4
  jmp shift_pipe_gap_power_ready

shift_pipe_gap_power8:
  imm r0 8

shift_pipe_gap_power_ready:
  mul0 r14
  subi0 1
  and0 r90
  mov r64 r0
  jc r64 shift_pipe_moving
  jmp shift_pipe_decode

; Shift occupancy and all five value bitplanes by the same mask.
shift_pipe_moving:
  add r90 r90 r64

  mov r0 r91
  and0 r64
  add0 r91
  mov r91 r0

  mov r0 r92
  and0 r64
  add0 r92
  mov r92 r0

  mov r0 r93
  and0 r64
  add0 r93
  mov r93 r0

  mov r0 r94
  and0 r64
  add0 r94
  mov r94 r0

  mov r0 r30
  and0 r64
  add0 r30
  mov r30 r0
  jmp shift_pipe_decode

shift_pipe_move_all:
  muli r90 r90 2
  muli r91 r91 2
  muli r92 r92 2
  muli r93 r93 2
  muli r94 r94 2
  muli r30 r30 2

shift_pipe_decode:
  and r62 r90 r18
  imm r63 0
  mov r0 r91
  and0 r41
  div0 r41
  add0 r63
  mov r63 r0
  mov r0 r92
  and0 r41
  div0 r41
  muli0 2
  add0 r63
  mov r63 r0
  mov r0 r93
  and0 r41
  div0 r41
  muli0 4
  add0 r63
  mov r63 r0
  mov r0 r94
  and0 r41
  div0 r41
  muli0 8
  add0 r63
  mov r63 r0
  mov r0 r30
  and0 r41
  div0 r41
  muli0 16
  add0 r63
  mov r63 r0

shift_pipe_save:
  jc r88 shift_pipe_save1

shift_pipe_save0:
  mov r75 r90
  mov r76 r91
  mov r4 r92
  mov r5 r93
  mov r6 r94
  mov r7 r30
  imm r3 0
  jc r62 shift_pipe0_source_ready
  imm r3 1

shift_pipe0_source_ready:
  mov r15 r63
  jeqs r87 1 shift_pipe1_missing
  imm r88 1
  jmp shift_pipe

shift_pipe1_missing:
  imm r56 0
  imm r57 0
  jmp shift_pipes_done

shift_pipe_save1:
  mov r85 r90
  mov r86 r91
  mov r9 r92
  mov r11 r93
  mov r12 r94
  mov r16 r30
  imm r56 0
  jc r62 shift_pipe1_source_ready
  imm r56 1

shift_pipe1_source_ready:
  mov r57 r63

shift_pipes_done:
  imm r58 0
  imm r59 0
  imm r60 0
  imm r61 0
  imm r17 0
  imm r66 0

execute_man:
  jeqs r66 0 execute_man_load0
  jeqs r66 1 execute_man_load1

execute_man_load2:
  mov r88 r42
  mov r89 r43
  mov r90 r44
  mov r91 r45
  mov r92 r46
  mov r93 r47
  mov r94 r48
  mov r30 r49
  mov r41 r50
  mov r52 r51
  jmp execute_man_loaded

execute_man_load0:
  mov r88 r20
  mov r89 r21
  mov r90 r22
  mov r91 r23
  mov r92 r24
  mov r93 r25
  mov r94 r26
  mov r30 r27
  mov r41 r28
  mov r52 r29
  jmp execute_man_loaded

execute_man_load1:
  mov r88 r31
  mov r89 r32
  mov r90 r33
  mov r91 r34
  mov r92 r35
  mov r93 r36
  mov r94 r37
  mov r30 r38
  mov r41 r39
  mov r52 r40

execute_man_loaded:
  jc r93 execute_man_save
  mov r0 r89
  mul0 r2
  add0 r88
  mov r54 r0
  load8 r10 r54 r62 r63 r64 r65

  jeqs r10 32 execute_move
  jeqs r10 64 execute_move
  jeqs r10 94 execute_up
  jeqs r10 62 execute_right
  jeqs r10 118 execute_down
  jeqs r10 60 execute_left
  jeqs r10 77 execute_m
  jeqs r10 43 execute_plus
  jeqs r10 45 execute_minus
  jeqs r10 88 execute_x
  jeqs r10 115 execute_send
  jeqs r10 114 execute_receive
  jeqs r10 72 execute_h

  subi r14 r10 47
  jc r14 execute_digit_high
  jmp execute_move

execute_digit_high:
  subi r14 r10 57
  jc r14 execute_move
  subi r91 r10 48
  jmp execute_move

execute_up:
  imm r90 0
  jmp execute_move

execute_right:
  imm r90 1
  jmp execute_move

execute_down:
  imm r90 2
  jmp execute_move

execute_left:
  imm r90 3
  jmp execute_move

execute_m:
  mov r92 r91
  jmp execute_move

execute_plus:
  add r91 r91 r92
  jmp execute_move

execute_minus:
  sub r91 r91 r92
  jmp execute_move

execute_x:
  jc r91 execute_x_clockwise
  mov r14 r91
  divi r14 r14 2
  neg r14
  jc r14 execute_x_counterclockwise
  jmp execute_move

execute_x_clockwise:
  inc r90
  subi r14 r90 3
  jc r14 execute_x_wrap_zero
  jmp execute_move

execute_x_wrap_zero:
  imm r90 0
  jmp execute_move

execute_x_counterclockwise:
  jc r90 execute_x_counter_nonzero
  imm r90 3
  jmp execute_move

execute_x_counter_nonzero:
  dec r90
  jmp execute_move

execute_h:
  imm r93 1
  jmp execute_man_save

execute_send:
  ; Choose the nearest outgoing pipe. Ties use endpoint reading order.
  jeqr r66 r68 execute_send_pipe0_match
  jmp execute_send_pipe1

execute_send_pipe0_match:
  jeqr r66 r78 execute_send_choose_nearest
  jmp execute_send_pipe0

execute_send_choose_nearest:
  mov r54 r70
  mov r14 r80
  jmp choose_nearest_pipe

execute_send_nearest_ready:
  jc r64 execute_send_pipe1

execute_send_pipe0:
  jc r3 execute_send_pipe0_ready
  jmp execute_man_save

execute_send_pipe0_ready:
  addi r58 r91 10
  imm r3 0
  jmp execute_move

execute_send_pipe1:
  jc r56 execute_send_pipe1_ready
  jmp execute_man_save

execute_send_pipe1_ready:
  addi r59 r91 10
  imm r56 0
  jmp execute_move

execute_receive:
  jeqr r66 r69 execute_receive_pipe0_match
  jmp execute_receive_pipe1

execute_receive_pipe0_match:
  jeqr r66 r79 execute_receive_choose_nearest
  jmp execute_receive_pipe0

execute_receive_choose_nearest:
  mov r54 r71
  mov r14 r81
  jmp choose_nearest_pipe

execute_receive_nearest_ready:
  jc r64 execute_receive_pipe1

execute_receive_pipe0:
  jc r15 execute_receive_pipe0_ready
  jmp execute_man_save

execute_receive_pipe0_ready:
  addi r91 r15 -10
  imm r60 1
  imm r15 0
  jmp execute_move

execute_receive_pipe1:
  jc r57 execute_receive_pipe1_ready
  jmp execute_man_save

execute_receive_pipe1_ready:
  addi r91 r57 -10
  imm r61 1
  imm r57 0
  jmp execute_move

choose_nearest_pipe:
  ; r54/r14 are packed endpoint positions. Return 0/1 in r64.
  divi r64 r54 16
  mov r0 r54
  andi0 15
  mov r62 r0
  sub r63 r88 r62
  jc r63 choose_p0_dx_ready
  neg r63

choose_p0_dx_ready:
  sub r64 r89 r64
  jc r64 choose_p0_dy_ready
  neg r64

choose_p0_dy_ready:
  add r63 r63 r64

  divi r65 r14 16
  mov r0 r14
  andi0 15
  mov r62 r0
  sub r64 r88 r62
  jc r64 choose_p1_dx_ready
  neg r64

choose_p1_dx_ready:
  sub r65 r89 r65
  jc r65 choose_p1_dy_ready
  neg r65

choose_p1_dy_ready:
  add r64 r64 r65

  sub r65 r63 r64
  jc r65 choose_pipe1
  neg r65
  jc r65 choose_pipe0

choose_tie:
  sub r65 r54 r14
  jc r65 choose_pipe1

choose_pipe0:
  imm r64 0
  jmp choose_nearest_return

choose_pipe1:
  imm r64 1

choose_nearest_return:
  jeqs r10 115 execute_send_nearest_ready
  jmp execute_receive_nearest_ready

execute_move:
  jeqs r90 0 execute_move_up
  jeqs r90 1 execute_move_right
  jeqs r90 2 execute_move_down

execute_move_left:
  dec r88
  jmp execute_wall_check

execute_move_up:
  dec r89
  jmp execute_wall_check

execute_move_right:
  inc r88
  jmp execute_wall_check

execute_move_down:
  inc r89

execute_wall_check:
  jeqrs r88 r94 execute_wall_hit
  jeqrs r88 r30 execute_wall_hit
  jeqrs r89 r41 execute_wall_hit
  jeqrs r89 r52 execute_wall_hit
  jmp execute_man_save

execute_wall_hit:
  imm r17 1

execute_man_save:
  jeqs r66 0 execute_man_save0
  jeqs r66 1 execute_man_save1

execute_man_save2:
  mov r42 r88
  mov r43 r89
  mov r44 r90
  mov r45 r91
  mov r46 r92
  mov r47 r93
  jmp execute_man_next

execute_man_save0:
  mov r20 r88
  mov r21 r89
  mov r22 r90
  mov r23 r91
  mov r24 r92
  mov r25 r93
  jmp execute_man_next

execute_man_save1:
  mov r31 r88
  mov r32 r89
  mov r33 r90
  mov r34 r91
  mov r35 r92
  mov r36 r93

execute_man_next:
  inc r66
  jeqrs r66 r13 apply_pipe_actions
  jmp execute_man

apply_pipe_actions:
  jc r60 apply_pipe0_receive

apply_pipe0_after_receive:
  jc r58 apply_pipe0_send

apply_pipe0_after_send:
  jc r61 apply_pipe1_receive

apply_pipe1_after_receive:
  jc r59 apply_pipe1_send

apply_pipe1_after_send:

  dec r19
  jc r17 render_halted

  ; Halt when all three slots are halted (missing slots start halted).
  jc r25 apply_check_halted1
  jmp tick_loop

apply_check_halted1:
  jc r36 apply_check_halted2
  jmp tick_loop

apply_check_halted2:
  jc r47 render_halted
  jmp tick_loop

apply_pipe0_receive:
  sub r75 r75 r8
  addi r14 r8 -1
  and r76 r76 r14
  and r4 r4 r14
  and r5 r5 r14
  and r6 r6 r14
  and r7 r7 r14
  jmp apply_pipe0_after_receive

apply_pipe0_send:
  inc r75
  mov r14 r58
  mov r0 r14
  and0 r18
  add0 r76
  mov r76 r0
  divi r62 r14 2
  mov r14 r62
  mov r0 r14
  and0 r18
  add0 r4
  mov r4 r0
  divi r62 r14 2
  mov r14 r62
  mov r0 r14
  and0 r18
  add0 r5
  mov r5 r0
  divi r62 r14 2
  mov r14 r62
  mov r0 r14
  and0 r18
  add0 r6
  mov r6 r0
  divi r62 r14 2
  mov r0 r62
  and0 r18
  add0 r7
  mov r7 r0
  jmp apply_pipe0_after_send

apply_pipe1_receive:
  sub r85 r85 r53
  addi r14 r53 -1
  and r86 r86 r14
  and r9 r9 r14
  and r11 r11 r14
  and r12 r12 r14
  and r16 r16 r14
  jmp apply_pipe1_after_receive

apply_pipe1_send:
  inc r85
  mov r14 r59
  mov r0 r14
  and0 r18
  add0 r86
  mov r86 r0
  divi r62 r14 2
  mov r14 r62
  mov r0 r14
  and0 r18
  add0 r9
  mov r9 r0
  divi r62 r14 2
  mov r14 r62
  mov r0 r14
  and0 r18
  add0 r11
  mov r11 r0
  divi r62 r14 2
  mov r14 r62
  mov r0 r14
  and0 r18
  add0 r12
  mov r12 r0
  divi r62 r14 2
  mov r0 r62
  and0 r18
  add0 r16
  mov r16 r0
  jmp apply_pipe1_after_send

render_halted:
  imm r19 1
  jmp render_pipes_start

render_pipes_start:
  imm r88 0

render_pipe:
  jc r88 render_pipe_load1

render_pipe_load0:
  mov r89 r67
  mov r90 r75
  mov r14 r75
  mov r63 r54
  mov r17 r72
  mov r62 r73
  mov r61 r74
  jmp render_pipe_loaded

render_pipe_load1:
  mov r89 r77
  mov r90 r85
  mov r14 r85
  mov r63 r55
  mov r17 r82
  mov r62 r83
  mov r61 r84

render_pipe_loaded:
  jeqr r14 r63 render_pipe_unchanged
  mov r60 r17

  .repeat 0 6
    render_pipe_cell_{i}:
    jeqs r89 {i} render_pipe_done
    mov r0 r60
    andi0 255
    mov r54 r0
    mov r0 r60
    divi0 256
    mov r60 r0

    and r63 r90 r18
    divi r90 r90 2
    imm r17 6
    jc r63 render_pipe_occupied_{i}
    jmp render_pipe_emit_{i}
    render_pipe_occupied_{i}:
    imm r17 14
    render_pipe_emit_{i}:
    screen_addr r54
    screen_data r17
  .endrepeat

  mov r60 r62

  .repeat 7 13
    render_pipe_cell_{i}:
    jeqs r89 {i} render_pipe_done
    mov r0 r60
    andi0 255
    mov r54 r0
    mov r0 r60
    divi0 256
    mov r60 r0

    and r63 r90 r18
    divi r90 r90 2
    imm r17 6
    jc r63 render_pipe_occupied_{i}
    jmp render_pipe_emit_{i}
    render_pipe_occupied_{i}:
    imm r17 14
    render_pipe_emit_{i}:
    screen_addr r54
    screen_data r17
  .endrepeat

  mov r60 r61

  .repeat 14 19
    render_pipe_cell_{i}:
    jeqs r89 {i} render_pipe_done
    mov r0 r60
    andi0 255
    mov r54 r0
    mov r0 r60
    divi0 256
    mov r60 r0

    and r63 r90 r18
    divi r90 r90 2
    imm r17 6
    jc r63 render_pipe_occupied_{i}
    jmp render_pipe_emit_{i}
    render_pipe_occupied_{i}:
    imm r17 14
    render_pipe_emit_{i}:
    screen_addr r54
    screen_data r17
  .endrepeat

render_pipe_done:
  jc r88 render_pipe_save1
  mov r54 r14
  jmp render_pipe_next

render_pipe_save1:
  mov r55 r14

render_pipe_unchanged:
render_pipe_next:
  jc r88 render_current_men
  jeqs r87 1 render_current_men
  imm r88 1
  jmp render_pipe

render_current_men:
  imm r17 9
  mov r0 r21
  muli0 16
  add0 r20
  mov r1 r0
  screen_addr r1
  screen_data r17
  subi r14 r13 1
  jc r14 render_current_man1
  jmp render_commit

render_current_man1:
  mov r0 r32
  muli0 16
  add0 r31
  mov r1 r0
  screen_addr r1
  screen_data r17
  subi r14 r13 2
  jc r14 render_current_man2
  jmp render_commit

render_current_man2:
  mov r0 r43
  muli0 16
  add0 r42
  mov r1 r0
  screen_addr r1
  screen_data r17

render_commit:
  screen_swap r18
  jc r19 halt
  jmp next_round

halt:
  jmp halt
