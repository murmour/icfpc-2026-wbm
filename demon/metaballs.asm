.screen 64 64

; Three moving fixed-point metaballs.
;
; Coordinates use 1/64 pixel units and field strength uses a scale of 1024.
;
; r2: center 0 x
; r3: center 0 y
; r4: center 1 x
; r5: center 1 y
; r6: center 2 x
; r7: center 2 y
; r8: ball 0 squared distance
; r9: pixel y
; r10: rows left
; r11: pixels left
; r12: field sum
; r13-r14: ball 1 and ball 2 squared distances
; r15, r28-r29: squared-distance scanline deltas
; r16-r27: oscillator (previous, current) pairs at scale 1,000,000

start:
  ; Ball 1 x: cos(1 + frame*0.016).
  imm r16 553696
  imm r17 540302

  ; Ball 1 y: sin(1 + frame*0.010).
  imm r18 836026
  imm r19 841471

  ; Ball 2 x: cos(2 + frame*0.032).
  imm r20 -386841
  imm r21 -416147

  ; Ball 2 y: sin(2 + frame*0.020).
  imm r22 917438
  imm r23 909297

  ; Ball 3 x: cos(3 + frame*0.048).
  imm r24 -982081
  imm r25 -989992

  ; Ball 3 y: sin(3 + frame*0.030).
  imm r26 170752
  imm r27 141120

frame:
  ; Convert oscillator values into 1/64-pixel coordinates.
  mov r2 r17
  muli r0 r2 1024
  divi0 1000000
  addi0 2048
  mov r2 r0

  mov r3 r19
  muli r0 r3 1024
  divi0 1000000
  addi0 2048
  mov r3 r0

  mov r4 r21
  muli r0 r4 1024
  divi0 1000000
  addi0 2048
  mov r4 r0

  mov r5 r23
  muli r0 r5 1024
  divi0 1000000
  addi0 2048
  mov r5 r0

  mov r6 r25
  muli r0 r6 1024
  divi0 1000000
  addi0 2048
  mov r6 r0

  mov r7 r27
  muli r0 r7 1024
  divi0 1000000
  addi0 2048
  mov r7 r0

  imm r9 0
  imm r10 64

row:
  ; Initialize the three squared distances at x=0. Since pixels are 64
  ; coordinate units apart, each delta increases by 2*64*64 = 8192.
  sub r0 r9 r3
  mul0 r0
  mov r8 r0
  mul r0 r2 r2
  add0 r8
  mov r8 r0
  muli r0 r2 -128
  addi0 4096
  mov r15 r0

  sub r0 r9 r5
  mul0 r0
  mov r13 r0
  mul r0 r4 r4
  add0 r13
  mov r13 r0
  muli r0 r4 -128
  addi0 4096
  mov r28 r0

  sub r0 r9 r7
  mul0 r0
  mov r14 r0
  mul r0 r6 r6
  add0 r14
  mov r14 r0
  muli r0 r6 -128
  addi0 4096
  mov r29 r0

  imm r11 64

pixel:
  imm r12 0

  ; Radius 6.4 field.
  mov r1 r12
  imm r0 171798692
  div0 r8
  add0 r1
  mov r12 r0

  ; Radius 9.6 field.
  mov r1 r12
  imm r0 386547057
  div0 r13
  add0 r1
  mov r12 r0

  ; Radius 12.8 field.
  mov r1 r12
  imm r0 687194767
  div0 r14
  add0 r1
  mov r12 r0

  ; Color bands for field values >4, >2, and >1.
  subi r0 r12 4096
  jc r0 core
  subi r0 r12 2048
  jc r0 middle
  subi r0 r12 1024
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

  add r8 r8 r15
  addi r15 r15 8192
  add r13 r13 r28
  addi r28 r28 8192
  add r14 r14 r29
  addi r29 r29 8192
  dec r11
  jc r11 pixel

  addi r9 r9 64
  dec r10
  jc r10 row

  imm r15 0
  screen_swap r15

  ; Ball 1 x oscillator.
  muli r0 r17 1999744
  divi0 1000000
  sub0 r16
  mov r16 r17
  mov r17 r0

  ; Ball 1 y oscillator.
  muli r0 r19 1999900
  divi0 1000000
  sub0 r18
  mov r18 r19
  mov r19 r0

  ; Ball 2 x oscillator.
  muli r0 r21 1998976
  divi0 1000000
  sub0 r20
  mov r20 r21
  mov r21 r0

  ; Ball 2 y oscillator.
  muli r0 r23 1999600
  divi0 1000000
  sub0 r22
  mov r22 r23
  mov r23 r0

  ; Ball 3 x oscillator.
  muli r0 r25 1997696
  divi0 1000000
  sub0 r24
  mov r24 r25
  mov r25 r0

  ; Ball 3 y oscillator.
  muli r0 r27 1999100
  divi0 1000000
  sub0 r26
  mov r26 r27
  mov r27 r0

  jmp frame
