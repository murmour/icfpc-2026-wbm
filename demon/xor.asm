.screen 64 64

; Multicolor radial XOR
;
; Oscillator states use a scale of 100,000,000.
;
; r2: frame
; r3: x1
; r4: y1
; r5: x2
; r6: y2
; r7: distance 1 scanline delta
; r8: distance 2 scanline delta
; r9: pixels
; r10: rows left
; r11: distance 1 squared
; r12: distance 2 squared
; r13: distance 1 band/temporary
; r14: distance 2 band/temporary
; r15: color
; r16-r23: oscillator (previous, current) pairs

start:
  imm r2 0
  imm r16 -1963369
  imm r18 99946459
  imm r19 100000000
  imm r20 2617695
  imm r22 -99946459
  imm r23 -100000000

frame:
  ; Convert oscillator amplitudes to pixel centers. Horizontal motion has
  ; amplitude 30; vertical motion has amplitude 20.
  muli r0 r17 3
  divi0 10000000
  addi0 32
  mov r3 r0

  divi r0 r19 5000000
  addi0 32
  mov r4 r0

  muli r0 r21 3
  divi0 10000000
  addi0 32
  mov r5 r0

  divi r0 r23 5000000
  addi0 32
  mov r6 r0

  imm r10 64

row:
  ; Initialize both squared distances at x=0. Their first differences
  ; advance the squared distances across the row using additions only.
  imm r0 64
  sub0 r10
  mov r13 r0

  mul r11 r3 r3
  sub r14 r13 r4
  mul r14 r14 r14
  add r11 r11 r14

  mul r12 r5 r5
  sub r14 r13 r6
  mul r14 r14 r14
  add r12 r12 r14

  muli r7 r3 -2
  inc r7
  muli r8 r5 -2
  inc r8
  imm r9 64

pixel:
  ; d1_band = floor(sqrt(d1_squared) / 8). The threshold tree compares
  ; against (8*k)^2 and therefore computes the exact visible distance bits.
  subi r0 r11 2303
  jc r0 d1_band_6_11
  subi r0 r11 575
  jc r0 d1_band_3_5
  subi r0 r11 255
  jc r0 d1_band_2
  subi r0 r11 63
  jc r0 d1_band_1
  imm r13 0
  jmp d1_band_ready

d1_band_1:
  imm r13 1
  jmp d1_band_ready

d1_band_2:
  imm r13 2
  jmp d1_band_ready

d1_band_3_5:
  subi r0 r11 1599
  jc r0 d1_band_5
  subi r0 r11 1023
  jc r0 d1_band_4
  imm r13 3
  jmp d1_band_ready

d1_band_4:
  imm r13 4
  jmp d1_band_ready

d1_band_5:
  imm r13 5
  jmp d1_band_ready

d1_band_6_11:
  subi r0 r11 5183
  jc r0 d1_band_9_11
  subi r0 r11 4095
  jc r0 d1_band_8
  subi r0 r11 3135
  jc r0 d1_band_7
  imm r13 6
  jmp d1_band_ready

d1_band_7:
  imm r13 7
  jmp d1_band_ready

d1_band_8:
  imm r13 8
  jmp d1_band_ready

d1_band_9_11:
  subi r0 r11 7743
  jc r0 d1_band_11
  subi r0 r11 6399
  jc r0 d1_band_10
  imm r13 9
  jmp d1_band_ready

d1_band_10:
  imm r13 10
  jmp d1_band_ready

d1_band_11:
  imm r13 11

d1_band_ready:
  ; Classify the second squared distance through the same thresholds.
  subi r0 r12 2303
  jc r0 d2_band_6_11
  subi r0 r12 575
  jc r0 d2_band_3_5
  subi r0 r12 255
  jc r0 d2_band_2
  subi r0 r12 63
  jc r0 d2_band_1
  imm r14 0
  jmp d2_band_ready

d2_band_1:
  imm r14 1
  jmp d2_band_ready

d2_band_2:
  imm r14 2
  jmp d2_band_ready

d2_band_3_5:
  subi r0 r12 1599
  jc r0 d2_band_5
  subi r0 r12 1023
  jc r0 d2_band_4
  imm r14 3
  jmp d2_band_ready

d2_band_4:
  imm r14 4
  jmp d2_band_ready

d2_band_5:
  imm r14 5
  jmp d2_band_ready

d2_band_6_11:
  subi r0 r12 5183
  jc r0 d2_band_9_11
  subi r0 r12 4095
  jc r0 d2_band_8
  subi r0 r12 3135
  jc r0 d2_band_7
  imm r14 6
  jmp d2_band_ready

d2_band_7:
  imm r14 7
  jmp d2_band_ready

d2_band_8:
  imm r14 8
  jmp d2_band_ready

d2_band_9_11:
  subi r0 r12 7743
  jc r0 d2_band_11
  subi r0 r12 6399
  jc r0 d2_band_10
  imm r14 9
  jmp d2_band_ready

d2_band_10:
  imm r14 10
  jmp d2_band_ready

d2_band_11:
  imm r14 11

d2_band_ready:
  ; pattern = d1_band XOR d2_band. Odd bands are black; even bands
  ; cycle through colors 10..15, advancing once every ten frames.
  mov r0 r13
  xor0 r14
  mov r13 r0
  andi0 1
  jc r0 pixel_black

  divi r14 r2 10
  add r0 r13 r14
  mov r14 r0
  divi0 6
  muli0 6
  mov r15 r0
  mov r0 r14
  sub0 r15
  addi0 10
  screen_data r0
  jmp pixel_done

pixel_black:
  imm r15 0
  screen_data r15

pixel_done:
  add r11 r11 r7
  addi r7 r7 2
  add r12 r12 r8
  addi r8 r8 2
  dec r9
  jc r9 pixel
  dec r10
  jc r10 row
  imm r15 0
  screen_swap r15

  ; x1: three turns per loop, 2*cos(w) = 1.99961448.
  muli r0 r17 199961448
  divi0 100000000
  sub0 r16
  mov r16 r17
  mov r17 r0

  ; y1: five turns per loop, 2*cos(w) = 1.99892917.
  muli r0 r19 199892917
  divi0 100000000
  sub0 r18
  mov r18 r19
  mov r19 r0

  ; x2: four turns per loop, 2*cos(w) = 1.99931465.
  muli r0 r21 199931465
  divi0 100000000
  sub0 r20
  mov r20 r21
  mov r21 r0

  ; y2: five turns per loop, 2*cos(w) = 1.99892917.
  muli r0 r23 199892917
  divi0 100000000
  sub0 r22
  mov r22 r23
  mov r23 r0

  inc r2
  jmp frame
