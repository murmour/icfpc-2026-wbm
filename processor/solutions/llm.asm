.screen 16 16
; Bulk source loading fills the storage ring before the fence read. Preserve
; two values per slot plus two control values on alternating pipe cells.
.memory 32 132
.kind llm

.reg width r2
.reg height r3

; Source loading aliases; these registers become pipe bitplanes afterwards.
.reg cells_total r4
.reg source_pos r5
.reg mem_addr r6
.reg packed r7
.reg factor r8
.reg pack_count r9
.reg cell r10
.reg x r11
.reg y r12
.reg man_count r13
.reg test r14
.reg p0_source r15
.reg display_addr r16
.reg color r17
.reg halt_action r17
.reg one r18
.reg rounds r19

; Pipe value bitplanes and destination masks.
.reg p0_plane1 r4
.reg p0_plane2 r5
.reg p0_plane3 r6
.reg p0_plane4 r7
.reg p0_dest r8
.reg p1_plane1 r9
.reg p1_plane2 r11
.reg p1_plane3 r12
.reg p1_plane4 r16
.reg p1_dest r53

; Persistent state for the three possible men.
.reg m0_x r20
.reg m0_y r21
.reg m0_dir r22
.reg m0_a r23
.reg m0_b r24
.reg m0_halted r25
.reg m0_left r26
.reg m0_right r27
.reg m0_top r28
.reg m0_bottom r29
.reg m0_prev r30

.reg m1_x r31
.reg m1_y r32
.reg m1_dir r33
.reg m1_a r34
.reg m1_b r35
.reg m1_halted r36
.reg m1_left r37
.reg m1_right r38
.reg m1_top r39
.reg m1_bottom r40
.reg m1_prev r41

.reg m2_x r42
.reg m2_y r43
.reg m2_dir r44
.reg m2_a r45
.reg m2_b r46
.reg m2_halted r47
.reg m2_left r48
.reg m2_right r49
.reg m2_top r50
.reg m2_bottom r51
.reg m2_prev r52

; Shared topology scratch. `room_idx` becomes pipe 1's destination mask.
.reg room_idx r53
.reg t0 r54
.reg t1 r55
.reg t2 r56
.reg t3 r57
.reg t4 r58
.reg t5 r59
.reg t6 r60
.reg t7 r61
.reg t8 r62
.reg t9 r63
.reg t10 r64
.reg t11 r65
.reg man_idx r66

; Persistent metadata for both pipes.
.reg p0_len r67
.reg p0_src r68
.reg p0_dst r69
.reg p0_first r70
.reg p0_last r71
.reg p0_path0 r72
.reg p0_path1 r73
.reg p0_path2 r74
.reg p0_occ r75
.reg p0_plane0 r76

.reg p1_len r77
.reg p1_src r78
.reg p1_dst r79
.reg p1_first r80
.reg p1_last r81
.reg p1_path0 r82
.reg p1_path1 r83
.reg p1_path2 r84
.reg p1_occ r85
.reg p1_plane0 r86
.reg pipe_count r87

; General workspace, aliased to the currently executing man's state.
.reg work0 r88
.reg work1 r89
.reg work2 r90
.reg work3 r91
.reg work4 r92
.reg work5 r93
.reg work6 r94
.reg cur_x r88
.reg cur_y r89
.reg cur_dir r90
.reg cur_a r91
.reg cur_b r92
.reg cur_halted r93
.reg cur_left r94
.reg cur_right r30
.reg cur_top r41
.reg cur_bottom r52
.reg room_right r30
.reg room_top r41
.reg room_bottom r52
.reg pipe_mask r41
.reg gap r52

; Interpret an LLM program containing up to three rooms and two pipes.
;
; Source memory:
;   0..31  eight row-major ASCII cells packed in base 256
;
; Each man keeps its position, direction, A/B registers, halted flag, room
; bounds, and previous display position in the corresponding `m0_*`/`m1_*`/
; `m2_*` registers.

start:
  read width
  read height
  mul cells_total width height

  imm source_pos 0
  imm mem_addr 0
  imm packed 0
  imm factor 1
  mov r0 factor
  imm pack_count 0
  imm x 0
  imm y 0
  imm man_count 0
  imm one 1

  ; Missing man slots are permanently halted.
  imm m0_halted 1
  imm m1_halted 1
  imm m2_halted 1

read_source:
  read cell

  ; Record each @ in row-major room order.
  subi test cell 64
  jc test read_not_at
  subi test cell 63
  jc test read_at
  jmp read_not_at

read_at:
  jeqs man_count 0 read_at_man0
  jeqs man_count 1 read_at_man1

read_at_man2:
  mov m2_x x
  mov m2_y y
  imm m2_dir 1
  imm m2_a 0
  imm m2_b 0
  imm m2_halted 0
  inc man_count
  jmp read_not_at

read_at_man0:
  mov m0_x x
  mov m0_y y
  imm m0_dir 1
  imm m0_a 0
  imm m0_b 0
  imm m0_halted 0
  inc man_count
  jmp read_not_at

read_at_man1:
  mov m1_x x
  mov m1_y y
  imm m1_dir 1
  imm m1_a 0
  imm m1_b 0
  imm m1_halted 0
  inc man_count

read_not_at:
  ; Paint a provisional cell while the source is already in hand. Room
  ; horizontals and all pipe cells are corrected after topology parsing.
  imm color 3
  jeqs cell 32 read_color_black
  jeqs cell 64 read_color_man
  jeqs cell 124 read_color_wall
  jeqs cell 43 read_color_arithmetic
  jeqs cell 45 read_color_arithmetic
  jeqs cell 77 read_color_blue
  jeqs cell 114 read_color_pipe_instruction
  jeqs cell 115 read_color_pipe_instruction
  subi test cell 47
  jc test read_color_digit_high
  jmp read_color_ready

read_color_digit_high:
  subi test cell 57
  jc test read_color_ready
  imm color 8
  jmp read_color_ready

read_color_black:
  imm color 0
  jmp read_color_ready

read_color_man:
  imm color 9
  jmp read_color_ready

read_color_wall:
  imm color 4
  jmp read_color_ready

read_color_arithmetic:
  imm color 10
  jmp read_color_ready

read_color_blue:
  imm color 12
  jmp read_color_ready

read_color_pipe_instruction:
  imm color 13

read_color_ready:
  screen_data color

  mov r0 cell
  mul0 factor
  add0 packed
  mov packed r0
  muli factor factor 256
  inc pack_count
  inc source_pos
  inc x

read_after_position:

  jeqs pack_count 8 read_flush

read_after_flush:
  jeqrs source_pos cells_total read_source_done
  jeqrs x width read_next_row
  jmp read_source

read_next_row:
  imm x 0
  inc y
  muli display_addr y 16
  screen_addr display_addr
  jmp read_source

read_flush:
  store mem_addr packed
  inc mem_addr
  imm packed 0
  imm factor 1
  mov r0 factor
  imm pack_count 0
  jmp read_after_flush

read_source_done:
  jc pack_count read_flush_final
  jmp source_stored

read_flush_final:
  store mem_addr packed

source_stored:
  ; A blocking read fences the asynchronous source stores.
  imm mem_addr 0
  load cell mem_addr

  ; Find each room's bounds from its @. A row scan reaches | walls;
  ; scanning the left wall vertically reaches + corners.
  imm room_idx 0

find_room:
  jeqs room_idx 0 find_room_load0
  jeqs room_idx 1 find_room_load1

find_room_load2:
  mov t0 m2_x
  mov t1 m2_y
  jmp find_left_start

find_room_load0:
  mov t0 m0_x
  mov t1 m0_y
  jmp find_left_start

find_room_load1:
  mov t0 m1_x
  mov t1 m1_y

find_left_start:
  mov t2 t0

find_left:
  dec t2
  mov r0 t1
  mul0 width
  add0 t2
  mov t6 r0
  load8 t7 t6 t8 t9 t10 t11
  jeqs t7 124 find_right_start
  jmp find_left

find_right_start:
  mov t3 t0

find_right:
  inc t3
  mov r0 t1
  mul0 width
  add0 t3
  mov t6 r0
  load8 t7 t6 t8 t9 t10 t11
  jeqs t7 124 find_top_start
  jmp find_right

find_top_start:
  mov t4 t1

find_top:
  dec t4
  mov r0 t4
  mul0 width
  add0 t2
  mov t6 r0
  load8 t7 t6 t8 t9 t10 t11
  jeqs t7 43 find_bottom_start
  jmp find_top

find_bottom_start:
  mov t5 t1

find_bottom:
  inc t5
  mov r0 t5
  mul0 width
  add0 t2
  mov t6 r0
  load8 t7 t6 t8 t9 t10 t11
  jeqs t7 43 find_room_save
  jmp find_bottom

find_room_save:
  jeqs room_idx 0 find_room_save0
  jeqs room_idx 1 find_room_save1

find_room_save2:
  mov m2_left t2
  mov m2_right t3
  mov m2_top t4
  mov m2_bottom t5
  jmp find_room_next

find_room_save0:
  mov m0_left t2
  mov m0_right t3
  mov m0_top t4
  mov m0_bottom t5
  jmp find_room_next

find_room_save1:
  mov m1_left t2
  mov m1_right t3
  mov m1_top t4
  mov m1_bottom t5

find_room_next:
  ; The streaming renderer treats '-' and '+' as instructions. Correct the
  ; two horizontal walls now that this room's bounds are known.
  imm color 4
  mov r0 t4
  muli0 16
  add0 t2
  mov display_addr r0
  screen_addr display_addr
  mov r0 t3
  sub0 t2
  addi0 1
  mov t6 r0

find_room_draw_top:
  screen_data color
  dec t6
  jc t6 find_room_draw_top

  mov r0 t5
  muli0 16
  add0 t2
  mov display_addr r0
  screen_addr display_addr
  mov r0 t3
  sub0 t2
  addi0 1
  mov t6 r0

find_room_draw_bottom:
  screen_data color
  dec t6
  jc t6 find_room_draw_bottom

  inc room_idx
  jeqrs room_idx man_count render_initial_start
  jmp find_room

render_initial_start:
  jmp parse_pipes_start

; Pipe metadata:
;             len src dst first last path0 path1 path2 occupancy plane0
;   pipe 0:   p0_len through p0_plane0
;   pipe 1:   p1_len through p1_plane0
;
; The remaining value bitplanes are p0_plane1..p0_plane4 for pipe 0 and
; p1_plane1,p1_plane2,p1_plane3,p1_plane4 for pipe 1. Destination masks are
; p0_dest and p1_dest.

parse_pipes_start:
  ; Force both paths to be painted on the initial frame.
  imm t0 -1
  imm t1 -1
  imm p0_len 0
  imm p0_src -1
  imm p0_dst -1
  imm p1_len 0
  imm p1_src -1
  imm p1_dst -1
  imm pipe_count 0
  imm work0 0

pipe_scan_room:
  jeqs work0 0 pipe_scan_room0
  jeqs work0 1 pipe_scan_room1

pipe_scan_room2:
  mov m2_prev m2_left
  mov t2 m2_right
  mov t3 m2_top
  mov color m2_bottom
  jmp pipe_scan_top_start

pipe_scan_room0:
  mov m2_prev m0_left
  mov t2 m0_right
  mov t3 m0_top
  mov color m0_bottom
  jmp pipe_scan_top_start

pipe_scan_room1:
  mov m2_prev m1_left
  mov t2 m1_right
  mov t3 m1_top
  mov color m1_bottom

pipe_scan_top_start:
  imm t1 0
  jc t3 pipe_scan_top_setup
  jmp pipe_scan_right_start

pipe_scan_top_setup:
  mov work2 m2_prev
  addi work3 t3 -1

pipe_scan_top:
  mov r0 work3
  mul0 width
  add0 work2
  mov work1 r0
  load8 cell work1 t8 t9 t10 t11
  jeqs cell 94 pipe_candidate_up

pipe_scan_top_next:
  inc work2
  sub test work2 t2
  jc test pipe_scan_right_start
  jmp pipe_scan_top

pipe_candidate_up:
  imm work5 0
  jmp pipe_trace_start

pipe_scan_right_start:
  imm t1 1
  addi work2 t2 1
  jeqrs work2 width pipe_scan_bottom_start
  mov work3 t3

pipe_scan_right:
  mov r0 work3
  mul0 width
  add0 work2
  mov work1 r0
  load8 cell work1 t8 t9 t10 t11
  jeqs cell 62 pipe_candidate_right

pipe_scan_right_next:
  inc work3
  sub test work3 color
  jc test pipe_scan_bottom_start
  jmp pipe_scan_right

pipe_candidate_right:
  imm work5 1
  jmp pipe_trace_start

pipe_scan_bottom_start:
  imm t1 2
  addi work3 color 1
  jeqrs work3 height pipe_scan_left_start
  mov work2 m2_prev

pipe_scan_bottom:
  mov r0 work3
  mul0 width
  add0 work2
  mov work1 r0
  load8 cell work1 t8 t9 t10 t11
  jeqs cell 118 pipe_candidate_down

pipe_scan_bottom_next:
  inc work2
  sub test work2 t2
  jc test pipe_scan_left_start
  jmp pipe_scan_bottom

pipe_candidate_down:
  imm work5 2
  jmp pipe_trace_start

pipe_scan_left_start:
  imm t1 3
  jc m2_prev pipe_scan_left_setup
  jmp pipe_scan_room_done

pipe_scan_left_setup:
  addi work2 m2_prev -1
  mov work3 t3

pipe_scan_left:
  mov r0 work3
  mul0 width
  add0 work2
  mov work1 r0
  load8 cell work1 t8 t9 t10 t11
  jeqs cell 60 pipe_candidate_left

pipe_scan_left_next:
  inc work3
  sub test work3 color
  jc test pipe_scan_room_done
  jmp pipe_scan_left

pipe_candidate_left:
  imm work5 3

pipe_trace_start:
  mov t4 work2
  mov t5 work3

  ; Keep the source room and first arrowhead.
  mov work6 work0
  mov r0 work3
  muli0 16
  add0 work2
  mov p1_plane1 r0
  imm p1_plane2 0
  imm p1_plane3 0
  imm p1_plane4 0
  imm m0_prev 0
  imm rounds 1
  mov r0 rounds
  imm work4 0
  imm t0 0
  imm work0 0
  imm p0_source 1

pipe_trace_append:
  mov r0 work3
  muli0 16
  add0 work2
  mov t8 r0
  mul0 rounds
  add0 m0_prev
  mov m0_prev r0
  muli rounds rounds 256
  inc work4
  inc t0
  muli p0_source p0_source 2
  jeqs t0 21 pipe_trace_overflow
  jeqs work4 7 pipe_trace_flush

pipe_trace_after_flush:

  jeqs work5 0 pipe_trace_move_up
  jeqs work5 1 pipe_trace_move_right
  jeqs work5 2 pipe_trace_move_down

pipe_trace_move_left:
  addi t7 work2 -1
  mov t6 work3
  jmp pipe_trace_moved

pipe_trace_move_up:
  mov t7 work2
  addi t6 work3 -1
  jmp pipe_trace_moved

pipe_trace_move_right:
  addi t7 work2 1
  mov t6 work3
  jmp pipe_trace_moved

pipe_trace_move_down:
  mov t7 work2
  addi t6 work3 1

pipe_trace_moved:
  ; A point inside any room is necessarily the destination border.
  sub test m0_left t7
  jc test pipe_trace_check_room1
  sub test t7 m0_right
  jc test pipe_trace_check_room1
  sub test m0_top t6
  jc test pipe_trace_check_room1
  sub test t6 m0_bottom
  jc test pipe_trace_check_room1
  imm man_idx 0
  jmp pipe_trace_done

pipe_trace_check_room1:
  subi test man_count 1
  jc test pipe_trace_check_room1_body
  jmp pipe_trace_check_room2

pipe_trace_check_room1_body:
  sub test m1_left t7
  jc test pipe_trace_check_room2
  sub test t7 m1_right
  jc test pipe_trace_check_room2
  sub test m1_top t6
  jc test pipe_trace_check_room2
  sub test t6 m1_bottom
  jc test pipe_trace_check_room2
  imm man_idx 1
  jmp pipe_trace_done

pipe_trace_check_room2:
  subi test man_count 2
  jc test pipe_trace_check_room2_body
  jmp pipe_trace_continue

pipe_trace_check_room2_body:
  sub test m2_left t7
  jc test pipe_trace_continue
  sub test t7 m2_right
  jc test pipe_trace_continue
  sub test m2_top t6
  jc test pipe_trace_continue
  sub test t6 m2_bottom
  jc test pipe_trace_continue
  imm man_idx 2
  jmp pipe_trace_done

pipe_trace_continue:
  mov work2 t7
  mov work3 t6
  mov test work2
  neg test
  jc test pipe_trace_overflow
  mov test work3
  neg test
  jc test pipe_trace_overflow
  jeqrs work2 width pipe_trace_overflow
  sub test work2 width
  jc test pipe_trace_overflow
  jeqrs work3 height pipe_trace_overflow
  sub test work3 height
  jc test pipe_trace_overflow
  mov r0 work3
  mul0 width
  add0 work2
  mov work1 r0
  load8 cell work1 t8 t9 t10 t11
  jeqs cell 94 pipe_trace_set_up
  jeqs cell 62 pipe_trace_set_right
  jeqs cell 118 pipe_trace_set_down
  jeqs cell 60 pipe_trace_set_left
  jmp pipe_trace_append

pipe_trace_set_up:
  imm work5 0
  jmp pipe_trace_append

pipe_trace_set_right:
  imm work5 1
  jmp pipe_trace_append

pipe_trace_set_down:
  imm work5 2
  jmp pipe_trace_append

pipe_trace_set_left:
  imm work5 3
  jmp pipe_trace_append

pipe_trace_overflow:
  imm man_idx 9
  jmp pipe_trace_done

pipe_trace_flush:
  jeqs work0 0 pipe_trace_flush0
  jeqs work0 1 pipe_trace_flush1

pipe_trace_flush2:
  mov p1_plane4 m0_prev
  jmp pipe_trace_flush_reset

pipe_trace_flush0:
  mov p1_plane2 m0_prev
  jmp pipe_trace_flush_reset

pipe_trace_flush1:
  mov p1_plane3 m0_prev

pipe_trace_flush_reset:
  inc work0
  imm m0_prev 0
  imm rounds 1
  mov r0 rounds
  imm work4 0
  jmp pipe_trace_after_flush

pipe_trace_done:
  divi p0_source p0_source 2

  ; Save a partial final path chunk.
  jc work4 pipe_trace_flush_final
  jmp pipe_trace_save

pipe_trace_flush_final:
  jeqs work0 0 pipe_trace_flush_final0
  jeqs work0 1 pipe_trace_flush_final1
  mov p1_plane4 m0_prev
  jmp pipe_trace_save

pipe_trace_flush_final0:
  mov p1_plane2 m0_prev
  jmp pipe_trace_save

pipe_trace_flush_final1:
  mov p1_plane3 m0_prev

pipe_trace_save:
  mov r0 work3
  muli0 16
  add0 work2
  mov t9 r0

  ; A bend beside another room can look like a second source. Such a ghost
  ; traces the same suffix and terminal cell as its parent. Keep the longest
  ; candidate for each terminal cell, matching the canonical pipe parser.
  imm work4 1
  jc pipe_count pipe_trace_compare0
  jmp pipe_trace_save0

pipe_trace_compare0:
  jeqrs t9 p0_last pipe_trace_same0
  subi test pipe_count 1
  jc test pipe_trace_compare1
  jmp pipe_trace_save1

pipe_trace_same0:
  sub test t0 p0_len
  jc test pipe_trace_replace0
  jmp pipe_scan_resume

pipe_trace_replace0:
  imm work4 0
  jmp pipe_trace_save0

pipe_trace_compare1:
  jeqrs t9 p1_last pipe_trace_same1
  jmp pipe_scan_resume

pipe_trace_same1:
  sub test t0 p1_len
  jc test pipe_trace_replace1
  jmp pipe_scan_resume

pipe_trace_replace1:
  imm work4 0
  jmp pipe_trace_save1

pipe_trace_save0:
  mov p0_len t0
  mov p0_src work6
  mov p0_dst man_idx
  mov p0_first p1_plane1
  mov p0_last t9
  mov p0_path0 p1_plane2
  mov p0_path1 p1_plane3
  mov p0_path2 p1_plane4
  imm p0_occ 0
  imm p0_plane0 0
  imm p0_plane1 0
  imm p0_plane2 0
  imm p0_plane3 0
  imm p0_plane4 0
  mov p0_dest p0_source
  jc work4 pipe_trace_increment_count
  jmp pipe_scan_resume

pipe_trace_save1:
  mov p1_len t0
  mov p1_src work6
  mov p1_dst man_idx
  mov p1_first p1_plane1
  mov p1_last t9
  mov p1_path0 p1_plane2
  mov p1_path1 p1_plane3
  mov p1_path2 p1_plane4
  imm p1_occ 0
  imm p1_plane0 0
  imm p1_plane1 0
  imm p1_plane2 0
  imm p1_plane3 0
  imm p1_plane4 0
  mov p1_dest p0_source
  jc work4 pipe_trace_increment_count
  jmp pipe_scan_resume

pipe_trace_increment_count:
  inc pipe_count

pipe_scan_resume:
  mov work0 work6
  mov work2 t4
  mov work3 t5
  jeqs t1 0 pipe_scan_top_next
  jeqs t1 1 pipe_scan_right_next
  jeqs t1 2 pipe_scan_bottom_next
  jmp pipe_scan_left_next

pipe_scan_room_done:
  inc work0
  jeqrs work0 man_count topology_ready
  jmp pipe_scan_room

topology_ready:
  ; These two runtime flags reuse dirty topology slots and otherwise relied
  ; on power-on zero. Every other reused temporary is assigned before use.
  imm t10 0
  imm rounds 0
  imm t0 -1
  imm t1 -1
  jmp render_pipes_start

next_round:
  read rounds

  ; Clear the old man pixels before executing. This frees the three previous
  ; position slots for runtime scratch throughout the tick loop.
  imm man_idx 0

render_restore_man:
  jeqs man_idx 0 render_restore_load0
  jeqs man_idx 1 render_restore_load1

render_restore_load2:
  mov r0 m2_y
  muli0 16
  add0 m2_x
  mov t0 r0
  mov work6 m2_left
  mov room_right m2_right
  mov room_top m2_top
  mov room_bottom m2_bottom
  jmp render_restore_loaded

render_restore_load0:
  mov r0 m0_y
  muli0 16
  add0 m0_x
  mov t0 r0
  mov work6 m0_left
  mov room_right m0_right
  mov room_top m0_top
  mov room_bottom m0_bottom
  jmp render_restore_loaded

render_restore_load1:
  mov r0 m1_y
  muli0 16
  add0 m1_x
  mov t0 r0
  mov work6 m1_left
  mov room_right m1_right
  mov room_top m1_top
  mov room_bottom m1_bottom

render_restore_loaded:
  divi work1 t0 16
  mov r0 t0
  andi0 15
  mov work0 r0
  jeqrs work0 work6 render_restore_wall
  jeqrs work0 room_right render_restore_wall
  jeqrs work1 room_top render_restore_wall
  jeqrs work1 room_bottom render_restore_wall
  mov r0 work1
  mul0 width
  add0 work0
  mov test r0
  load8 cell test t8 t9 t10 t11
  jeqs cell 32 render_restore_black
  jeqs cell 64 render_restore_black
  jeqs cell 43 render_restore_arithmetic
  jeqs cell 45 render_restore_arithmetic
  subi test cell 47
  jc test render_restore_digit_or_symbol
  jmp render_restore_yellow

render_restore_digit_or_symbol:
  subi test cell 57
  jc test render_restore_symbol
  imm color 8
  jmp render_restore_emit

render_restore_symbol:
  jeqs cell 77 render_restore_blue
  jeqs cell 114 render_restore_pipe_instruction
  jeqs cell 115 render_restore_pipe_instruction

render_restore_yellow:
  imm color 3
  jmp render_restore_emit

render_restore_arithmetic:
  imm color 10
  jmp render_restore_emit

render_restore_blue:
  imm color 12
  jmp render_restore_emit

render_restore_pipe_instruction:
  imm color 13
  jmp render_restore_emit

render_restore_wall:
  imm color 4
  jmp render_restore_emit

render_restore_black:
  imm color 0

render_restore_emit:
  screen_addr t0
  screen_data color
  inc man_idx
  jeqrs man_idx man_count tick_loop
  jmp render_restore_man

tick_loop:
  jc rounds execute_tick
  jmp render_pipes_start

execute_tick:
  imm work0 0

shift_pipe:
  jc work0 shift_pipe_load1

shift_pipe_load0:
  mov work1 p0_len
  mov work2 p0_occ
  mov work3 p0_plane0
  mov work4 p0_plane1
  mov work5 p0_plane2
  mov work6 p0_plane3
  mov m0_prev p0_plane4
  mov m1_prev p0_dest
  jmp shift_pipe_loaded

shift_pipe_load1:
  mov work1 p1_len
  mov work2 p1_occ
  mov work3 p1_plane0
  mov work4 p1_plane1
  mov work5 p1_plane2
  mov work6 p1_plane3
  mov m0_prev p1_plane4
  mov m1_prev p1_dest

shift_pipe_loaded:
  jc work1 shift_pipe_begin
  imm t8 1
  imm t9 0
  jmp shift_pipe_save

shift_pipe_begin:
  jc work2 shift_pipe_nonempty
  imm t8 0
  imm t9 0
  jmp shift_pipe_save

shift_pipe_nonempty:
  ; Pipes update destination-to-source. An empty destination lets every token
  ; advance. Otherwise, find the highest gap: every token below it advances,
  ; while the packed suffix above it remains in place.
  mov r0 pipe_mask
  muli0 2
  subi0 1
  mov test r0
  sub cell test work2
  and gap cell pipe_mask
  jc gap shift_pipe_move_all
  jc cell shift_pipe_find_gap
  jmp shift_pipe_decode

shift_pipe_find_gap:
  ; Normalize the highest nonzero nibble of the empty-cell mask.
  subi gap cell 255
  jc gap shift_pipe_gap_above8
  subi gap cell 15
  jc gap shift_pipe_gap4

shift_pipe_gap0:
  mov gap cell
  imm test 1
  jmp shift_pipe_gap_nibble

shift_pipe_gap4:
  divi gap cell 16
  imm test 16
  jmp shift_pipe_gap_nibble

shift_pipe_gap_above8:
  subi gap cell 4095
  jc gap shift_pipe_gap_above12

shift_pipe_gap8:
  divi gap cell 256
  imm test 256
  jmp shift_pipe_gap_nibble

shift_pipe_gap_above12:
  subi gap cell 65535
  jc gap shift_pipe_gap16

shift_pipe_gap12:
  divi gap cell 4096
  imm test 4096
  jmp shift_pipe_gap_nibble

shift_pipe_gap16:
  divi gap cell 65536
  imm test 65536

shift_pipe_gap_nibble:
  ; Highest power of two in the four-bit `gap` value.
  mov r0 gap
  subi0 7
  jc r0 shift_pipe_gap_power8
  mov r0 gap
  subi0 3
  jc r0 shift_pipe_gap_power4
  mov r0 gap
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
  mul0 test
  subi0 1
  and0 work2
  mov t10 r0
  jc t10 shift_pipe_moving
  jmp shift_pipe_decode

; Shift occupancy and all five value bitplanes by the same mask.
shift_pipe_moving:
  add work2 work2 t10

  mov r0 work3
  and0 t10
  add0 work3
  mov work3 r0

  mov r0 work4
  and0 t10
  add0 work4
  mov work4 r0

  mov r0 work5
  and0 t10
  add0 work5
  mov work5 r0

  mov r0 work6
  and0 t10
  add0 work6
  mov work6 r0

  mov r0 m0_prev
  and0 t10
  add0 m0_prev
  mov m0_prev r0
  jmp shift_pipe_decode

shift_pipe_move_all:
  muli work2 work2 2
  muli work3 work3 2
  muli work4 work4 2
  muli work5 work5 2
  muli work6 work6 2
  muli m0_prev m0_prev 2

shift_pipe_decode:
  and t8 work2 one
  imm t9 0
  mov r0 work3
  and0 pipe_mask
  div0 pipe_mask
  add0 t9
  mov t9 r0
  mov r0 work4
  and0 pipe_mask
  div0 pipe_mask
  muli0 2
  add0 t9
  mov t9 r0
  mov r0 work5
  and0 pipe_mask
  div0 pipe_mask
  muli0 4
  add0 t9
  mov t9 r0
  mov r0 work6
  and0 pipe_mask
  div0 pipe_mask
  muli0 8
  add0 t9
  mov t9 r0
  mov r0 m0_prev
  and0 pipe_mask
  div0 pipe_mask
  muli0 16
  add0 t9
  mov t9 r0

shift_pipe_save:
  jc work0 shift_pipe_save1

shift_pipe_save0:
  mov p0_occ work2
  mov p0_plane0 work3
  mov p0_plane1 work4
  mov p0_plane2 work5
  mov p0_plane3 work6
  mov p0_plane4 m0_prev
  imm height 0
  jc t8 shift_pipe0_source_ready
  imm height 1

shift_pipe0_source_ready:
  mov p0_source t9
  jeqs pipe_count 1 shift_pipe1_missing
  imm work0 1
  jmp shift_pipe

shift_pipe1_missing:
  imm t2 0
  imm t3 0
  jmp shift_pipes_done

shift_pipe_save1:
  mov p1_occ work2
  mov p1_plane0 work3
  mov p1_plane1 work4
  mov p1_plane2 work5
  mov p1_plane3 work6
  mov p1_plane4 m0_prev
  imm t2 0
  jc t8 shift_pipe1_source_ready
  imm t2 1

shift_pipe1_source_ready:
  mov t3 t9

shift_pipes_done:
  imm t4 0
  imm t5 0
  imm t6 0
  imm t7 0
  imm halt_action 0
  imm man_idx 0

execute_man:
  jeqs man_idx 0 execute_man_load0
  jeqs man_idx 1 execute_man_load1

execute_man_load2:
  mov cur_x m2_x
  mov cur_y m2_y
  mov cur_dir m2_dir
  mov cur_a m2_a
  mov cur_b m2_b
  mov cur_halted m2_halted
  mov cur_left m2_left
  mov cur_right m2_right
  mov cur_top m2_top
  mov cur_bottom m2_bottom
  jmp execute_man_loaded

execute_man_load0:
  mov cur_x m0_x
  mov cur_y m0_y
  mov cur_dir m0_dir
  mov cur_a m0_a
  mov cur_b m0_b
  mov cur_halted m0_halted
  mov cur_left m0_left
  mov cur_right m0_right
  mov cur_top m0_top
  mov cur_bottom m0_bottom
  jmp execute_man_loaded

execute_man_load1:
  mov cur_x m1_x
  mov cur_y m1_y
  mov cur_dir m1_dir
  mov cur_a m1_a
  mov cur_b m1_b
  mov cur_halted m1_halted
  mov cur_left m1_left
  mov cur_right m1_right
  mov cur_top m1_top
  mov cur_bottom m1_bottom

execute_man_loaded:
  jc cur_halted execute_man_save
  mov r0 cur_y
  mul0 width
  add0 cur_x
  mov t0 r0
  load8 cell t0 t8 t9 t10 t11

  jeqs cell 32 execute_move
  jeqs cell 64 execute_move
  jeqs cell 94 execute_up
  jeqs cell 62 execute_right
  jeqs cell 118 execute_down
  jeqs cell 60 execute_left
  jeqs cell 77 execute_m
  jeqs cell 43 execute_plus
  jeqs cell 45 execute_minus
  jeqs cell 88 execute_x
  jeqs cell 115 execute_send
  jeqs cell 114 execute_receive
  jeqs cell 72 execute_h

  subi test cell 47
  jc test execute_digit_high
  jmp execute_move

execute_digit_high:
  subi test cell 57
  jc test execute_move
  subi cur_a cell 48
  jmp execute_move

execute_up:
  imm cur_dir 0
  jmp execute_move

execute_right:
  imm cur_dir 1
  jmp execute_move

execute_down:
  imm cur_dir 2
  jmp execute_move

execute_left:
  imm cur_dir 3
  jmp execute_move

execute_m:
  mov cur_b cur_a
  jmp execute_move

execute_plus:
  add cur_a cur_a cur_b
  jmp execute_move

execute_minus:
  sub cur_a cur_a cur_b
  jmp execute_move

execute_x:
  jc cur_a execute_x_clockwise
  mov test cur_a
  divi test test 2
  neg test
  jc test execute_x_counterclockwise
  jmp execute_move

execute_x_clockwise:
  inc cur_dir
  subi test cur_dir 3
  jc test execute_x_wrap_zero
  jmp execute_move

execute_x_wrap_zero:
  imm cur_dir 0
  jmp execute_move

execute_x_counterclockwise:
  jc cur_dir execute_x_counter_nonzero
  imm cur_dir 3
  jmp execute_move

execute_x_counter_nonzero:
  dec cur_dir
  jmp execute_move

execute_h:
  imm cur_halted 1
  jmp execute_man_save

execute_send:
  ; Choose the nearest outgoing pipe. Ties use endpoint reading order.
  jeqr man_idx p0_src execute_send_pipe0_match
  jmp execute_send_pipe1

execute_send_pipe0_match:
  jeqr man_idx p1_src execute_send_choose_nearest
  jmp execute_send_pipe0

execute_send_choose_nearest:
  mov t0 p0_first
  mov test p1_first
  jmp choose_nearest_pipe

execute_send_nearest_ready:
  jc t10 execute_send_pipe1

execute_send_pipe0:
  jc height execute_send_pipe0_ready
  jmp execute_man_save

execute_send_pipe0_ready:
  addi t4 cur_a 10
  imm height 0
  jmp execute_move

execute_send_pipe1:
  jc t2 execute_send_pipe1_ready
  jmp execute_man_save

execute_send_pipe1_ready:
  addi t5 cur_a 10
  imm t2 0
  jmp execute_move

execute_receive:
  jeqr man_idx p0_dst execute_receive_pipe0_match
  jmp execute_receive_pipe1

execute_receive_pipe0_match:
  jeqr man_idx p1_dst execute_receive_choose_nearest
  jmp execute_receive_pipe0

execute_receive_choose_nearest:
  mov t0 p0_last
  mov test p1_last
  jmp choose_nearest_pipe

execute_receive_nearest_ready:
  jc t10 execute_receive_pipe1

execute_receive_pipe0:
  jc p0_source execute_receive_pipe0_ready
  jmp execute_man_save

execute_receive_pipe0_ready:
  addi cur_a p0_source -10
  imm t6 1
  imm p0_source 0
  jmp execute_move

execute_receive_pipe1:
  jc t3 execute_receive_pipe1_ready
  jmp execute_man_save

execute_receive_pipe1_ready:
  addi cur_a t3 -10
  imm t7 1
  imm t3 0
  jmp execute_move

choose_nearest_pipe:
  ; t0/test are packed endpoint positions. Return 0/1 in t10.
  divi t10 t0 16
  mov r0 t0
  andi0 15
  mov t8 r0
  sub t9 cur_x t8
  jc t9 choose_p0_dx_ready
  neg t9

choose_p0_dx_ready:
  sub t10 cur_y t10
  jc t10 choose_p0_dy_ready
  neg t10

choose_p0_dy_ready:
  add t9 t9 t10

  divi t11 test 16
  mov r0 test
  andi0 15
  mov t8 r0
  sub t10 cur_x t8
  jc t10 choose_p1_dx_ready
  neg t10

choose_p1_dx_ready:
  sub t11 cur_y t11
  jc t11 choose_p1_dy_ready
  neg t11

choose_p1_dy_ready:
  add t10 t10 t11

  sub t11 t9 t10
  jc t11 choose_pipe1
  neg t11
  jc t11 choose_pipe0

choose_tie:
  sub t11 t0 test
  jc t11 choose_pipe1

choose_pipe0:
  imm t10 0
  jmp choose_nearest_return

choose_pipe1:
  imm t10 1

choose_nearest_return:
  jeqs cell 115 execute_send_nearest_ready
  jmp execute_receive_nearest_ready

execute_move:
  jeqs cur_dir 0 execute_move_up
  jeqs cur_dir 1 execute_move_right
  jeqs cur_dir 2 execute_move_down

execute_move_left:
  dec cur_x
  jmp execute_wall_check

execute_move_up:
  dec cur_y
  jmp execute_wall_check

execute_move_right:
  inc cur_x
  jmp execute_wall_check

execute_move_down:
  inc cur_y

execute_wall_check:
  jeqrs cur_x cur_left execute_wall_hit
  jeqrs cur_x cur_right execute_wall_hit
  jeqrs cur_y cur_top execute_wall_hit
  jeqrs cur_y cur_bottom execute_wall_hit
  jmp execute_man_save

execute_wall_hit:
  imm halt_action 1

execute_man_save:
  jeqs man_idx 0 execute_man_save0
  jeqs man_idx 1 execute_man_save1

execute_man_save2:
  mov m2_x cur_x
  mov m2_y cur_y
  mov m2_dir cur_dir
  mov m2_a cur_a
  mov m2_b cur_b
  mov m2_halted cur_halted
  jmp execute_man_next

execute_man_save0:
  mov m0_x cur_x
  mov m0_y cur_y
  mov m0_dir cur_dir
  mov m0_a cur_a
  mov m0_b cur_b
  mov m0_halted cur_halted
  jmp execute_man_next

execute_man_save1:
  mov m1_x cur_x
  mov m1_y cur_y
  mov m1_dir cur_dir
  mov m1_a cur_a
  mov m1_b cur_b
  mov m1_halted cur_halted

execute_man_next:
  inc man_idx
  jeqrs man_idx man_count apply_pipe_actions
  jmp execute_man

apply_pipe_actions:
  jc t6 apply_pipe0_receive

apply_pipe0_after_receive:
  jc t4 apply_pipe0_send

apply_pipe0_after_send:
  jc t7 apply_pipe1_receive

apply_pipe1_after_receive:
  jc t5 apply_pipe1_send

apply_pipe1_after_send:

  dec rounds
  jc halt_action render_halted

  ; Halt when all three slots are halted (missing slots start halted).
  jc m0_halted apply_check_halted1
  jmp tick_loop

apply_check_halted1:
  jc m1_halted apply_check_halted2
  jmp tick_loop

apply_check_halted2:
  jc m2_halted render_halted
  jmp tick_loop

apply_pipe0_receive:
  sub p0_occ p0_occ p0_dest
  addi test p0_dest -1
  and p0_plane0 p0_plane0 test
  and p0_plane1 p0_plane1 test
  and p0_plane2 p0_plane2 test
  and p0_plane3 p0_plane3 test
  and p0_plane4 p0_plane4 test
  jmp apply_pipe0_after_receive

apply_pipe0_send:
  inc p0_occ
  mov test t4
  mov r0 test
  and0 one
  add0 p0_plane0
  mov p0_plane0 r0
  divi t8 test 2
  mov test t8
  mov r0 test
  and0 one
  add0 p0_plane1
  mov p0_plane1 r0
  divi t8 test 2
  mov test t8
  mov r0 test
  and0 one
  add0 p0_plane2
  mov p0_plane2 r0
  divi t8 test 2
  mov test t8
  mov r0 test
  and0 one
  add0 p0_plane3
  mov p0_plane3 r0
  divi t8 test 2
  mov r0 t8
  and0 one
  add0 p0_plane4
  mov p0_plane4 r0
  jmp apply_pipe0_after_send

apply_pipe1_receive:
  sub p1_occ p1_occ p1_dest
  addi test p1_dest -1
  and p1_plane0 p1_plane0 test
  and p1_plane1 p1_plane1 test
  and p1_plane2 p1_plane2 test
  and p1_plane3 p1_plane3 test
  and p1_plane4 p1_plane4 test
  jmp apply_pipe1_after_receive

apply_pipe1_send:
  inc p1_occ
  mov test t5
  mov r0 test
  and0 one
  add0 p1_plane0
  mov p1_plane0 r0
  divi t8 test 2
  mov test t8
  mov r0 test
  and0 one
  add0 p1_plane1
  mov p1_plane1 r0
  divi t8 test 2
  mov test t8
  mov r0 test
  and0 one
  add0 p1_plane2
  mov p1_plane2 r0
  divi t8 test 2
  mov test t8
  mov r0 test
  and0 one
  add0 p1_plane3
  mov p1_plane3 r0
  divi t8 test 2
  mov r0 t8
  and0 one
  add0 p1_plane4
  mov p1_plane4 r0
  jmp apply_pipe1_after_send

render_halted:
  imm rounds 1
  jmp render_pipes_start

render_pipes_start:
  imm work0 0

render_pipe:
  jc work0 render_pipe_load1

render_pipe_load0:
  mov work1 p0_len
  mov work2 p0_occ
  mov test p0_occ
  mov t9 t0
  mov color p0_path0
  mov t8 p0_path1
  mov t7 p0_path2
  jmp render_pipe_loaded

render_pipe_load1:
  mov work1 p1_len
  mov work2 p1_occ
  mov test p1_occ
  mov t9 t1
  mov color p1_path0
  mov t8 p1_path1
  mov t7 p1_path2

render_pipe_loaded:
  jeqr test t9 render_pipe_unchanged
  mov t6 color

  .repeat 0 6
    render_pipe_cell_{i}:
    jeqs work1 {i} render_pipe_done
    mov r0 t6
    andi0 255
    mov t0 r0
    mov r0 t6
    divi0 256
    mov t6 r0

    and t9 work2 one
    divi work2 work2 2
    imm color 6
    jc t9 render_pipe_occupied_{i}
    jmp render_pipe_emit_{i}
    render_pipe_occupied_{i}:
    imm color 14
    render_pipe_emit_{i}:
    screen_addr t0
    screen_data color
  .endrepeat

  mov t6 t8

  .repeat 7 13
    render_pipe_cell_{i}:
    jeqs work1 {i} render_pipe_done
    mov r0 t6
    andi0 255
    mov t0 r0
    mov r0 t6
    divi0 256
    mov t6 r0

    and t9 work2 one
    divi work2 work2 2
    imm color 6
    jc t9 render_pipe_occupied_{i}
    jmp render_pipe_emit_{i}
    render_pipe_occupied_{i}:
    imm color 14
    render_pipe_emit_{i}:
    screen_addr t0
    screen_data color
  .endrepeat

  mov t6 t7

  .repeat 14 19
    render_pipe_cell_{i}:
    jeqs work1 {i} render_pipe_done
    mov r0 t6
    andi0 255
    mov t0 r0
    mov r0 t6
    divi0 256
    mov t6 r0

    and t9 work2 one
    divi work2 work2 2
    imm color 6
    jc t9 render_pipe_occupied_{i}
    jmp render_pipe_emit_{i}
    render_pipe_occupied_{i}:
    imm color 14
    render_pipe_emit_{i}:
    screen_addr t0
    screen_data color
  .endrepeat

render_pipe_done:
  jc work0 render_pipe_save1
  mov t0 test
  jmp render_pipe_next

render_pipe_save1:
  mov t1 test

render_pipe_unchanged:
render_pipe_next:
  jc work0 render_current_men
  jeqs pipe_count 1 render_current_men
  imm work0 1
  jmp render_pipe

render_current_men:
  imm color 9
  mov r0 m0_y
  muli0 16
  add0 m0_x
  mov r1 r0
  screen_addr r1
  screen_data color
  subi test man_count 1
  jc test render_current_man1
  jmp render_commit

render_current_man1:
  mov r0 m1_y
  muli0 16
  add0 m1_x
  mov r1 r0
  screen_addr r1
  screen_data color
  subi test man_count 2
  jc test render_current_man2
  jmp render_commit

render_current_man2:
  mov r0 m2_y
  muli0 16
  add0 m2_x
  mov r1 r0
  screen_addr r1
  screen_data color

render_commit:
  screen_swap one
  jc rounds halt
  jmp next_round

halt:
  jmp halt
