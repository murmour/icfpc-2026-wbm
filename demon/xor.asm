.screen 64 64

; Multicolor radial XOR
;
; Oscillator states use a scale of 100,000,000.

.reg frame r2
.reg x1 r3
.reg y1 r4
.reg x2 r5
.reg y2 r6
.reg d1_scanline_delta r7
.reg d2_scanline_delta r8
.reg pixels r9
.reg rows_left r10
.reg dist1_squared r11
.reg dist2_squared r12
.reg dist1_band r13
.reg dist2_band r14
.reg color r15
.reg oscillator[8] r16

start:
  imm frame 0
  imm oscillator[0] -1963369
  imm oscillator[2] 99946459
  imm oscillator[3] 100000000
  imm oscillator[4] 2617695
  imm oscillator[6] -99946459
  imm oscillator[7] -100000000

frame:
  ; Convert oscillator amplitudes to pixel centers. Horizontal motion has
  ; amplitude 30; vertical motion has amplitude 20.
  muli r0 oscillator[1] 3
  divi0 10000000
  addi0 32
  mov x1 r0

  divi r0 oscillator[3] 5000000
  addi0 32
  mov y1 r0

  muli r0 oscillator[5] 3
  divi0 10000000
  addi0 32
  mov x2 r0

  divi r0 oscillator[7] 5000000
  addi0 32
  mov y2 r0

  imm rows_left 64

row:
  ; Initialize both squared distances at x=0. Their first differences
  ; advance the squared distances across the row using additions only.
  imm r0 64
  sub0 rows_left
  mov dist1_band r0

  mul dist1_squared x1 x1
  sub dist2_band dist1_band y1
  mul dist2_band dist2_band dist2_band
  add dist1_squared dist1_squared dist2_band

  mul dist2_squared x2 x2
  sub dist2_band dist1_band y2
  mul dist2_band dist2_band dist2_band
  add dist2_squared dist2_squared dist2_band

  muli d1_scanline_delta x1 -2
  inc d1_scanline_delta
  muli d2_scanline_delta x2 -2
  inc d2_scanline_delta
  imm pixels 64

pixel:
  ; d1_band = floor(sqrt(d1_squared) / 8). The threshold tree compares
  ; against (8*k)^2 and therefore computes the exact visible distance bits.
  subi r0 dist1_squared 2303
  jc r0 d1_band_6_11
  subi r0 dist1_squared 575
  jc r0 d1_band_3_5
  subi r0 dist1_squared 255
  jc r0 d1_band_2
  subi r0 dist1_squared 63
  jc r0 d1_band_1
  imm dist1_band 0
  jmp d1_band_ready

d1_band_1:
  imm dist1_band 1
  jmp d1_band_ready

d1_band_2:
  imm dist1_band 2
  jmp d1_band_ready

d1_band_3_5:
  subi r0 dist1_squared 1599
  jc r0 d1_band_5
  subi r0 dist1_squared 1023
  jc r0 d1_band_4
  imm dist1_band 3
  jmp d1_band_ready

d1_band_4:
  imm dist1_band 4
  jmp d1_band_ready

d1_band_5:
  imm dist1_band 5
  jmp d1_band_ready

d1_band_6_11:
  subi r0 dist1_squared 5183
  jc r0 d1_band_9_11
  subi r0 dist1_squared 4095
  jc r0 d1_band_8
  subi r0 dist1_squared 3135
  jc r0 d1_band_7
  imm dist1_band 6
  jmp d1_band_ready

d1_band_7:
  imm dist1_band 7
  jmp d1_band_ready

d1_band_8:
  imm dist1_band 8
  jmp d1_band_ready

d1_band_9_11:
  subi r0 dist1_squared 7743
  jc r0 d1_band_11
  subi r0 dist1_squared 6399
  jc r0 d1_band_10
  imm dist1_band 9
  jmp d1_band_ready

d1_band_10:
  imm dist1_band 10
  jmp d1_band_ready

d1_band_11:
  imm dist1_band 11

d1_band_ready:
  ; Classify the second squared distance through the same thresholds.
  subi r0 dist2_squared 2303
  jc r0 d2_band_6_11
  subi r0 dist2_squared 575
  jc r0 d2_band_3_5
  subi r0 dist2_squared 255
  jc r0 d2_band_2
  subi r0 dist2_squared 63
  jc r0 d2_band_1
  imm dist2_band 0
  jmp d2_band_ready

d2_band_1:
  imm dist2_band 1
  jmp d2_band_ready

d2_band_2:
  imm dist2_band 2
  jmp d2_band_ready

d2_band_3_5:
  subi r0 dist2_squared 1599
  jc r0 d2_band_5
  subi r0 dist2_squared 1023
  jc r0 d2_band_4
  imm dist2_band 3
  jmp d2_band_ready

d2_band_4:
  imm dist2_band 4
  jmp d2_band_ready

d2_band_5:
  imm dist2_band 5
  jmp d2_band_ready

d2_band_6_11:
  subi r0 dist2_squared 5183
  jc r0 d2_band_9_11
  subi r0 dist2_squared 4095
  jc r0 d2_band_8
  subi r0 dist2_squared 3135
  jc r0 d2_band_7
  imm dist2_band 6
  jmp d2_band_ready

d2_band_7:
  imm dist2_band 7
  jmp d2_band_ready

d2_band_8:
  imm dist2_band 8
  jmp d2_band_ready

d2_band_9_11:
  subi r0 dist2_squared 7743
  jc r0 d2_band_11
  subi r0 dist2_squared 6399
  jc r0 d2_band_10
  imm dist2_band 9
  jmp d2_band_ready

d2_band_10:
  imm dist2_band 10
  jmp d2_band_ready

d2_band_11:
  imm dist2_band 11

d2_band_ready:
  ; pattern = d1_band XOR d2_band. Odd bands are black; even bands
  ; cycle through colors 10..15, advancing once every ten frames.
  mov r0 dist1_band
  xor0 dist2_band
  mov dist1_band r0
  andi0 1
  jc r0 pixel_black

  divi dist2_band frame 10
  add r0 dist1_band dist2_band
  mov dist2_band r0
  divi0 6
  muli0 6
  mov color r0
  mov r0 dist2_band
  sub0 color
  addi0 10
  screen_data r0
  jmp pixel_done

pixel_black:
  imm color 0
  screen_data color

pixel_done:
  add dist1_squared dist1_squared d1_scanline_delta
  addi d1_scanline_delta d1_scanline_delta 2
  add dist2_squared dist2_squared d2_scanline_delta
  addi d2_scanline_delta d2_scanline_delta 2
  dec pixels
  jc pixels pixel
  dec rows_left
  jc rows_left row
  imm color 0
  screen_swap color

  ; x1: three turns per loop, 2*cos(w) = 1.99961448.
  muli r0 oscillator[1] 199961448
  divi0 100000000
  sub0 oscillator[0]
  mov oscillator[0] oscillator[1]
  mov oscillator[1] r0

  ; y1: five turns per loop, 2*cos(w) = 1.99892917.
  muli r0 oscillator[3] 199892917
  divi0 100000000
  sub0 oscillator[2]
  mov oscillator[2] oscillator[3]
  mov oscillator[3] r0

  ; x2: four turns per loop, 2*cos(w) = 1.99931465.
  muli r0 oscillator[5] 199931465
  divi0 100000000
  sub0 oscillator[4]
  mov oscillator[4] oscillator[5]
  mov oscillator[5] r0

  ; y2: five turns per loop, 2*cos(w) = 1.99892917.
  muli r0 oscillator[7] 199892917
  divi0 100000000
  sub0 oscillator[6]
  mov oscillator[6] oscillator[7]
  mov oscillator[7] r0

  inc frame
  jmp frame
