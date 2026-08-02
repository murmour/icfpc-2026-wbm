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
; r8: pixel x
; r9: pixel y
; r10: rows left
; r11: pixels left
; r12: field sum
; r13-r15: temporaries
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
  imm r8 0
  imm r11 64

pixel:
  imm r12 0

  ; Radius 6.4 field.
  sub r0 r8 r2
  mul0 r0
  mov r13 r0
  sub r0 r9 r3
  mul0 r0
  mov r14 r0
  add r13 r13 r14
  jc r13 ball0_nonzero
  jmp ball0_done

ball0_nonzero:
  imm r14 171798692
  div r15 r14 r13
  add r12 r12 r15

ball0_done:
  ; Radius 9.6 field.
  sub r0 r8 r4
  mul0 r0
  mov r13 r0
  sub r0 r9 r5
  mul0 r0
  mov r14 r0
  add r13 r13 r14
  jc r13 ball1_nonzero
  jmp ball1_done

ball1_nonzero:
  imm r14 386547057
  div r15 r14 r13
  add r12 r12 r15

ball1_done:
  ; Radius 12.8 field.
  sub r0 r8 r6
  mul0 r0
  mov r13 r0
  sub r0 r9 r7
  mul0 r0
  mov r14 r0
  add r13 r13 r14
  jc r13 ball2_nonzero
  jmp ball2_done

ball2_nonzero:
  imm r14 687194767
  div r15 r14 r13
  add r12 r12 r15

ball2_done:
  ; Color bands for field values >4, >2, and >1.
  subi r13 r12 4096
  jc r13 core
  subi r13 r12 2048
  jc r13 middle
  subi r13 r12 1024
  jc r13 edge
  imm r15 0
  jmp emit

core:
  imm r15 1
  jmp emit

middle:
  imm r15 14
  jmp emit

edge:
  imm r15 6

emit:
  screen_data r15

  addi r8 r8 64
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
