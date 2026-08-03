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
.reg wave1_angle r3
.reg y r4
.reg rows r5
.reg pixels r6
.reg sum r7
.reg angle r8
.reg abs_angle r9
.reg row_wave r10
.reg dx r11
.reg dy r12
.reg wave3_angle r15


start:
  imm phase 0

frame:
  imm y 0
  imm rows 64

row:
  imm pixels 64
  ; The first and third wave angles advance by fixed amounts across a row.
  ; Store each angle minus 1799, so positivity detects wraparound directly.
  muli wave1_angle phase 4
  subi wave1_angle wave1_angle 1799

wave1_seed_wrap:
  jc wave1_angle wave1_seed_subtract_turn
  jmp wave2

wave1_seed_subtract_turn:
  subi wave1_angle wave1_angle 3600
  jmp wave1_seed_wrap

wave2:
  ; sin(y*0.5 - frame*1.5) is constant across the row
  muli angle y 5
  muli abs_angle phase 3
  sub angle angle abs_angle

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
  imm r0 1800
  sub0 abs_angle
  mul0 angle
  divi0 791
  mov row_wave r0
  ; abs(y-32) is also constant across the row
  subi dy y 32
  jc dy distance_dy_ready
  neg dy

distance_dy_ready:
  ; seed sin((x+y)*0.4 + frame*1.0)
  muli wave3_angle y 4
  muli abs_angle phase 2
  add wave3_angle wave3_angle abs_angle
  subi wave3_angle wave3_angle 1799

wave3_seed_wrap:
  jc wave3_angle wave3_seed_subtract_turn
  jmp pixel

wave3_seed_subtract_turn:
  subi wave3_angle wave3_angle 3600
  jmp wave3_seed_wrap

pixel:
  mov sum row_wave
  ; sin(x*0.8 + frame*2.0)
  addi angle wave1_angle 1799
  mov abs_angle angle
  jc abs_angle wave1_abs_ready
  neg abs_angle

wave1_abs_ready:
  imm r0 1800
  sub0 abs_angle
  mul0 angle
  divi0 791
  add0 sum
  mov sum r0

  addi wave1_angle wave1_angle 8
  jc wave1_angle wave1_subtract_turn
  jmp wave3_sine

wave1_subtract_turn:
  subi wave1_angle wave1_angle 3600

wave3_sine:
  ; sin((x+y)*0.4 + frame*1.0)
  addi angle wave3_angle 1799
  mov abs_angle angle
  jc abs_angle wave3_abs_ready
  neg abs_angle

wave3_abs_ready:
  imm r0 1800
  sub0 abs_angle
  mul0 angle
  divi0 791
  add0 sum
  mov sum r0

  addi wave3_angle wave3_angle 4
  jc wave3_angle wave3_subtract_turn
  jmp distance

wave3_subtract_turn:
  subi wave3_angle wave3_angle 3600

distance:
  ; approximate hypot(x-32, y-32)
  subi dx pixels 32
  jc dx distance_dx_ready
  neg dx

distance_dx_ready:
  sub r0 dx dy
  jc r0 distance_dx_larger
  ; abs(dy) >= abs(dx)
  muli r0 dx 3
  divi0 8
  add0 dy
  jmp distance_ready

distance_dx_larger:
  muli r0 dy 3
  divi0 8
  add0 dx

distance_ready:
  ; sin(distance*0.3 - frame*0.5)
  muli0 3
  sub0 phase
  mov angle r0

wave4_lower:
  imm r0 -1800
  sub0 angle
  jc r0 wave4_add_turn
  jmp wave4_sine

wave4_add_turn:
  addi angle angle 3600

wave4_sine:
  mov abs_angle angle
  jc abs_angle wave4_abs_ready
  neg abs_angle

wave4_abs_ready:
  imm r0 1800
  sub0 abs_angle
  mul0 angle
  divi0 791
  add0 sum
  mov sum r0
  ; original mapping: ((value + 4.0) * 2.0) % 16
  addi r0 sum 4096
  divi0 512
  mov sum r0
  subi r0 sum 15
  jc r0 color_wrap
  jmp emit

color_wrap:
  subi sum sum 16

emit:
  screen_data sum
  dec pixels
  jc pixels pixel
  inc y
  dec rows
  jc rows row
  imm r0 0
  screen_swap r0
  ; One frame is 0.5 degrees in the shared phase.
  ; It yields the source's +2.0, -1.5, +1.0, and -0.5 degree wave velocities.
  addi phase phase 5
  subi r0 phase 3599
  jc r0 phase_wrap
  jmp frame

phase_wrap:
  subi phase phase 3600
  jmp frame
