; Three moving fixed-point metaballs.
;
; Coordinates use 1/64 pixel units and field strength uses a scale of 1024.

.screen 64 64

.reg ball0_x r2
.reg ball0_y r3
.reg ball1_x r4
.reg ball1_y r5
.reg ball2_x r6
.reg ball2_y r7
.reg d0 r8
.reg y r9
.reg rows r10
.reg pixels r11
.reg field r12
.reg d1 r13
.reg d2 r14
.reg d0_delta r15
.reg osc[12] r16
.reg d1_delta r28
.reg d2_delta r29


start:
  ; Ball 1 x: cos(1 + frame*0.016).
  imm osc[0] 553696
  imm osc[1] 540302

  ; Ball 1 y: sin(1 + frame*0.010).
  imm osc[2] 836026
  imm osc[3] 841471

  ; Ball 2 x: cos(2 + frame*0.032).
  imm osc[4] -386841
  imm osc[5] -416147

  ; Ball 2 y: sin(2 + frame*0.020).
  imm osc[6] 917438
  imm osc[7] 909297

  ; Ball 3 x: cos(3 + frame*0.048).
  imm osc[8] -982081
  imm osc[9] -989992

  ; Ball 3 y: sin(3 + frame*0.030).
  imm osc[10] 170752
  imm osc[11] 141120

frame:
  ; Convert oscillator values into 1/64-pixel coordinates.
  mov ball0_x osc[1]
  muli r0 ball0_x 1024
  divi0 1000000
  addi0 2048
  mov ball0_x r0

  mov ball0_y osc[3]
  muli r0 ball0_y 1024
  divi0 1000000
  addi0 2048
  mov ball0_y r0

  mov ball1_x osc[5]
  muli r0 ball1_x 1024
  divi0 1000000
  addi0 2048
  mov ball1_x r0

  mov ball1_y osc[7]
  muli r0 ball1_y 1024
  divi0 1000000
  addi0 2048
  mov ball1_y r0

  mov ball2_x osc[9]
  muli r0 ball2_x 1024
  divi0 1000000
  addi0 2048
  mov ball2_x r0

  mov ball2_y osc[11]
  muli r0 ball2_y 1024
  divi0 1000000
  addi0 2048
  mov ball2_y r0

  imm y 0
  imm rows 64

row:
  ; Initialize the three squared distances at x=0. Since pixels are 64
  ; coordinate units apart, each delta increases by 2*64*64 = 8192.
  sub r0 y ball0_y
  mul0 r0
  mov d0 r0
  mul r0 ball0_x ball0_x
  add0 d0
  mov d0 r0
  muli r0 ball0_x -128
  addi0 4096
  mov d0_delta r0

  sub r0 y ball1_y
  mul0 r0
  mov d1 r0
  mul r0 ball1_x ball1_x
  add0 d1
  mov d1 r0
  muli r0 ball1_x -128
  addi0 4096
  mov d1_delta r0

  sub r0 y ball2_y
  mul0 r0
  mov d2 r0
  mul r0 ball2_x ball2_x
  add0 d2
  mov d2 r0
  muli r0 ball2_x -128
  addi0 4096
  mov d2_delta r0

  imm pixels 64

pixel:
  imm field 0

  ; Radius 6.4 field.
  mov r1 field
  imm r0 171798692
  div0 d0
  add0 r1
  mov field r0

  ; Radius 9.6 field.
  mov r1 field
  imm r0 386547057
  div0 d1
  add0 r1
  mov field r0

  ; Radius 12.8 field.
  mov r1 field
  imm r0 687194767
  div0 d2
  add0 r1
  mov field r0

  ; Color bands for field values >4, >2, and >1.
  subi r0 field 4096
  jc r0 core
  subi r0 field 2048
  jc r0 middle
  subi r0 field 1024
  jc r0 edge
  imm r1 0
  jmp emit

core:
  imm r1 1
  jmp emit

middle:
  imm r1 14
  jmp emit

edge:
  imm r1 6

emit:
  screen_data r1

  add d0 d0 d0_delta
  addi d0_delta d0_delta 8192
  add d1 d1 d1_delta
  addi d1_delta d1_delta 8192
  add d2 d2 d2_delta
  addi d2_delta d2_delta 8192
  dec pixels
  jc pixels pixel

  addi y y 64
  dec rows
  jc rows row

  imm d0_delta 0
  screen_swap d0_delta

  ; Ball 1 x oscillator.
  muli r0 osc[1] 1999744
  divi0 1000000
  sub0 osc[0]
  mov osc[0] osc[1]
  mov osc[1] r0

  ; Ball 1 y oscillator.
  muli r0 osc[3] 1999900
  divi0 1000000
  sub0 osc[2]
  mov osc[2] osc[3]
  mov osc[3] r0

  ; Ball 2 x oscillator.
  muli r0 osc[5] 1998976
  divi0 1000000
  sub0 osc[4]
  mov osc[4] osc[5]
  mov osc[5] r0

  ; Ball 2 y oscillator.
  muli r0 osc[7] 1999600
  divi0 1000000
  sub0 osc[6]
  mov osc[6] osc[7]
  mov osc[7] r0

  ; Ball 3 x oscillator.
  muli r0 osc[9] 1997696
  divi0 1000000
  sub0 osc[8]
  mov osc[8] osc[9]
  mov osc[9] r0

  ; Ball 3 y oscillator.
  muli r0 osc[11] 1999100
  divi0 1000000
  sub0 osc[10]
  mov osc[10] osc[11]
  mov osc[11] r0

  jmp frame
