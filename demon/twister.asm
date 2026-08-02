.screen 64 64

.reg roll r2
.reg row_phase r3
.reg t0 r4
.reg t1 r5
.reg t2 r6
.reg t3 r7
.reg left r8
.reg split r9
.reg right r10
.reg x r11
.reg face_x r12
.reg rows r13
.reg row_step r14
.reg face_width r15

; Four-sided scanline twister.
;
; The reference effect indexes a 512-entry table with:
;
;   roll + y * 1.2 * sin(14*pi*roll/512) * cos(2*pi*roll/512)
;
; We evaluate the same expression in fixed point, then approximate sine with
; x * (1800 - abs(x)) / 791. Angles are measured in tenths of a degree and
; sine values are scaled by 1024.

; Start near a maximum bend so the first frame is already visibly twisted.
start:
  imm roll 40

frame:
  ; sin(14*pi*roll/512): angle = roll * 1575/32 tenths of a degree.
  divi r0 roll 2
  muli0 1575
  divi0 32
  mov row_phase r0

high_wrap:
  subi r0 row_phase 1799
  jc r0 high_subtract_turn
  jmp high_ready

high_subtract_turn:
  subi row_phase row_phase 3600
  jmp high_wrap

high_ready:
  mov t0 row_phase
  mov t1 row_phase
  jc t1 high_abs_ready
  neg t1

high_abs_ready:
  imm t2 1800
  sub t2 t2 t1
  mul r0 t0 t2
  divi0 791
  mov t0 r0

  ; cos(2*pi*roll/512) = sin(roll * 225/32 + 90 degrees).
  divi r0 roll 2
  muli0 225
  divi0 32
  addi0 900
  mov row_phase r0

low_wrap:
  subi r0 row_phase 1799
  jc r0 low_subtract_turn
  jmp low_ready

low_subtract_turn:
  subi row_phase row_phase 3600
  jmp low_wrap

low_ready:
  mov t1 row_phase
  mov t2 row_phase
  jc t2 low_abs_ready
  neg t2

low_abs_ready:
  imm t3 1800
  sub t3 t3 t2
  mul r0 t1 t3
  divi0 791
  mov t1 r0

  ; row_step is 1.2*sin(high)*cos(low), scaled by 1024.
  mul r0 t0 t1
  muli0 12
  divi0 10240
  mov row_step r0

  divi r0 roll 2
  muli0 1024
  mov row_phase r0
  imm rows 64

row:
  ; Convert the fixed-point phase to the reference's truncation toward zero.
  mov t2 row_phase
  jc t2 row_phase_positive
  addi t2 t2 1023

row_phase_positive:
  divi t2 t2 1024

; Wrap the table index into 0..511.
wouaf_lower:
  jc t2 wouaf_upper
  addi t2 t2 512
  jmp wouaf_upper

wouaf_subtract:
  subi t2 t2 512

wouaf_upper:
  subi r0 t2 511
  jc r0 wouaf_subtract

  ; theta = 3*pi*wouaf/512 = wouaf * 675/64 tenths of a degree.
  muli r0 t2 675
  divi0 64
  mov t3 r0
  subi0 1799
  jc r0 theta_subtract_turn
  jmp theta_ready

theta_subtract_turn:
  subi t3 t3 3600

theta_ready:
  ; t0 = sin(theta).
  mov t0 t3
  mov t1 t3
  jc t1 theta_abs_ready
  neg t1

theta_abs_ready:
  imm t2 1800
  sub t2 t2 t1
  mul r0 t0 t2
  divi0 791
  mov t0 r0

  ; t1 = cos(theta) = sin(theta + 90 degrees).
  addi t3 t3 900
  subi0 1799
  jc r0 cosine_subtract_turn
  jmp cosine_ready

cosine_subtract_turn:
  subi t3 t3 3600

cosine_ready:
  mov t1 t3
  mov t2 t3
  jc t2 cosine_abs_ready
  neg t2

cosine_abs_ready:
  imm t3 1800
  sub t3 t3 t2
  mul r0 t1 t3
  divi0 791
  mov t1 r0

  ; Project the square's four vertices around x=32 with radius 28.
  muli r0 t0 28
  divi0 1024
  addi0 32
  mov t0 r0
  imm t2 64
  sub t2 t2 t0

  muli r0 t1 28
  divi0 1024
  addi0 32
  mov t1 r0
  imm t3 64
  sub t3 t3 t1

  ; Choose the leftmost vertex and the next two cyclic vertices.
  ; They are the left edge, the face, and the right edge of the visible half of the square.
  subi r0 t0 32
  jc r0 sine_positive
  subi r0 t1 32
  jc r0 quadrant_4

  ; Both sine and cosine are non-positive.
  sub r0 t0 t1
  jc r0 front_2
  jmp front_1

quadrant_4:
  ; cosine > -sine
  add r0 t0 t1
  subi0 64
  jc r0 front_0
  jmp front_1

sine_positive:
  subi r0 t1 32
  jc r0 quadrant_1

  ; sine > -cosine
  add r0 t0 t1
  subi0 64
  jc r0 front_3
  jmp front_2

quadrant_1:
  ; cosine > sine
  sub r0 t1 t0
  jc r0 front_0
  jmp front_3

front_0:
  mov left t3
  mov split t0
  mov right t1
  jmp draw_row

front_1:
  mov left t0
  mov split t1
  mov right t2
  jmp draw_row

front_2:
  mov left t1
  mov split t2
  mov right t3
  jmp draw_row

front_3:
  mov left t2
  mov split t3
  mov right t0

draw_row:
  imm x 0

pixel:
  ; Black outside the silhouette.
  sub r0 x left
  addi0 1
  jc r0 after_left
  imm r0 0
  jmp emit

after_left:
  sub r0 right x
  addi0 1
  jc r0 inside
  imm r0 0
  jmp emit

inside:
  ; Express x relative to either visible face.
  sub r0 split x
  jc r0 first_face
  sub face_x x split
  sub face_width right split
  jmp shade

first_face:
  sub face_x x left
  sub face_width split left

shade:
  ; Reproduce twister_zoom's four equal color bands.
  divi r0 face_width 4
  sub0 face_x
  jc r0 color_red

  divi r0 face_width 2
  sub0 face_x
  jc r0 color_green

  divi t2 face_width 4
  divi r0 face_width 2
  add0 t2
  sub0 face_x
  jc r0 color_yellow

  imm r0 3
  jmp emit

color_red:
  imm r0 2
  jmp emit

color_green:
  imm r0 5
  jmp emit

color_yellow:
  imm r0 7

emit:
  screen_data r0
  inc x
  subi r0 x 63
  jc r0 row_done
  jmp pixel

row_done:
  add row_phase row_phase row_step
  dec rows
  jc rows row

  imm r0 0
  screen_swap r0

  ; Three half-index steps are 1.5 table entries (to slow down).
  addi roll roll 3
  subi0 1021
  jc r0 roll_wrap
  jmp frame

roll_wrap:
  subi roll roll 1022
  jmp frame
