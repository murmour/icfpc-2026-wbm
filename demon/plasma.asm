; Four-wave plasma.
;
; Angles use tenths of a degree.
;
; Sine uses the signed parabolic approximation:
;   x * (1800 - abs(x)) / 791,
; producing values near [-1024, 1024].
;
; Hypot uses:
;   max(abs(dx), abs(dy)) + 3/8 * min(abs(dx), abs(dy)).

.screen 64 64

.reg phase r2
.reg x r3
.reg y r4
.reg rows r5
.reg pixels r6
.reg sum r7
.reg angle r8
.reg abs_angle r9
.reg sine r10
.reg dx r11
.reg dy r12
.reg distance r13
.reg test r14
.reg color r15


start:
  imm phase 0

frame:
  imm y 0
  imm rows 64

row:
  imm x 0
  imm pixels 64

pixel:
  imm sum 0

  ; sin(x*0.8 + frame*2.0)
  muli angle x 8
  muli abs_angle phase 4
  add angle angle abs_angle

wave1_upper:
  subi r0 angle 1799
  jc r0 wave1_subtract_turn
  jmp wave1_lower

wave1_subtract_turn:
  subi angle angle 3600
  jmp wave1_upper

wave1_lower:
  imm r0 -1800
  sub0 angle
  jc r0 wave1_add_turn
  jmp wave1_sine

wave1_add_turn:
  addi angle angle 3600
  jmp wave1_lower

wave1_sine:
  mov abs_angle angle
  jc abs_angle wave1_abs_ready
  neg abs_angle

wave1_abs_ready:
  imm sine 1800
  sub r0 sine abs_angle
  mul0 angle
  divi0 791
  mov sine r0
  add sum sum sine

  ; sin(y*0.5 - frame*1.5)
  muli angle y 5
  muli abs_angle phase 3
  sub angle angle abs_angle

wave2_upper:
  subi r0 angle 1799
  jc r0 wave2_subtract_turn
  jmp wave2_lower

wave2_subtract_turn:
  subi angle angle 3600
  jmp wave2_upper

wave2_lower:
  imm r0 -1800
  sub0 angle
  jc r0 wave2_add_turn
  jmp wave2_sine

wave2_add_turn:
  addi angle angle 3600
  jmp wave2_lower

wave2_sine:
  mov abs_angle angle
  jc abs_angle wave2_abs_ready
  neg abs_angle

wave2_abs_ready:
  imm sine 1800
  sub r0 sine abs_angle
  mul0 angle
  divi0 791
  mov sine r0
  add sum sum sine

  ; sin((x+y)*0.4 + frame*1.0)
  add r0 x y
  muli0 4
  mov angle r0
  muli abs_angle phase 2
  add angle angle abs_angle

wave3_upper:
  subi r0 angle 1799
  jc r0 wave3_subtract_turn
  jmp wave3_lower

wave3_subtract_turn:
  subi angle angle 3600
  jmp wave3_upper

wave3_lower:
  imm r0 -1800
  sub0 angle
  jc r0 wave3_add_turn
  jmp wave3_sine

wave3_add_turn:
  addi angle angle 3600
  jmp wave3_lower

wave3_sine:
  mov abs_angle angle
  jc abs_angle wave3_abs_ready
  neg abs_angle

wave3_abs_ready:
  imm sine 1800
  sub r0 sine abs_angle
  mul0 angle
  divi0 791
  mov sine r0
  add sum sum sine

  ; Approximate hypot(x-32, y-32).
  subi dx x 32
  jc dx distance_dx_ready
  neg dx

distance_dx_ready:
  subi dy y 32
  jc dy distance_dy_ready
  neg dy

distance_dy_ready:

  sub r0 dx dy
  jc r0 distance_dx_larger

  ; abs(dy) >= abs(dx)
  muli r0 dx 3
  divi0 8
  mov distance r0
  add distance dy distance
  jmp distance_ready

distance_dx_larger:
  muli r0 dy 3
  divi0 8
  mov distance r0
  add distance dx distance

distance_ready:
  ; sin(distance*0.3 - frame*0.5)
  muli r0 distance 3
  sub0 phase
  mov angle r0

wave4_upper:
  subi r0 angle 1799
  jc r0 wave4_subtract_turn
  jmp wave4_lower

wave4_subtract_turn:
  subi angle angle 3600
  jmp wave4_upper

wave4_lower:
  imm r0 -1800
  sub0 angle
  jc r0 wave4_add_turn
  jmp wave4_sine

wave4_add_turn:
  addi angle angle 3600
  jmp wave4_lower

wave4_sine:
  mov abs_angle angle
  jc abs_angle wave4_abs_ready
  neg abs_angle

wave4_abs_ready:
  imm sine 1800
  sub r0 sine abs_angle
  mul0 angle
  divi0 791
  mov sine r0
  add sum sum sine

  ; Original mapping: ((value + 4.0) * 2.0) % 16.
  addi r0 sum 4096
  divi0 512
  mov color r0
  subi test color 15
  jc test color_wrap
  jmp emit

color_wrap:
  subi color color 16

emit:
  screen_data color

  inc x
  dec pixels
  jc pixels pixel

  inc y
  dec rows
  jc rows row

  imm r0 0
  screen_swap r0

  ; One frame is 0.5 degrees in the shared phase. It yields the source's
  ; +2.0, -1.5, +1.0, and -0.5 degree wave velocities.
  addi phase phase 5
  subi r0 phase 3599
  jc r0 phase_wrap
  jmp frame

phase_wrap:
  subi phase phase 3600
  jmp frame
