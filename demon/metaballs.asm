.screen 64 64
.memory 17

; Three moving fixed-point metaballs based on demoserv/effect_metaballs.c.
; Coordinates use 1/64 pixel units and field strength uses a scale of 1024.
;
; r2,r3   center 0      r8,r9   pixel x,y
; r4,r5   center 1      r10,r11 row/pixel counters
; r6,r7   center 2      r12     field sum
; r13-r15 temporaries

; Memory stores (previous, current) oscillator samples at scale 1,000,000.
; Ball 1 x: cos(1 + frame*0.016).
imm r13 0
imm r14 553696
store r13 r14
imm r13 1
imm r14 540302
store r13 r14

; Ball 1 y: sin(1 + frame*0.010).
imm r13 2
imm r14 836026
store r13 r14
imm r13 3
imm r14 841471
store r13 r14

; Ball 2 x: cos(2 + frame*0.032).
imm r13 4
imm r14 -386841
store r13 r14
imm r13 5
imm r14 -416147
store r13 r14

; Ball 2 y: sin(2 + frame*0.020).
imm r13 6
imm r14 917438
store r13 r14
imm r13 7
imm r14 909297
store r13 r14

; Ball 3 x: cos(3 + frame*0.048).
imm r13 8
imm r14 -982081
store r13 r14
imm r13 9
imm r14 -989992
store r13 r14

; Ball 3 y: sin(3 + frame*0.030).
imm r13 10
imm r14 170752
store r13 r14
imm r13 11
imm r14 141120
store r13 r14

frame:
; Convert oscillator values into 1/64-pixel coordinates.
imm r13 1
load r2 r13
muli r0 r2 1024
divi0 1000000
addi0 2048
mov r2 r0

imm r13 3
load r3 r13
muli r0 r3 1024
divi0 1000000
addi0 2048
mov r3 r0

imm r13 5
load r4 r13
muli r0 r4 1024
divi0 1000000
addi0 2048
mov r4 r0

imm r13 7
load r5 r13
muli r0 r5 1024
divi0 1000000
addi0 2048
mov r5 r0

imm r13 9
load r6 r13
muli r0 r6 1024
divi0 1000000
addi0 2048
mov r6 r0

imm r13 11
load r7 r13
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
imm r13 0
load r8 r13
imm r13 1
load r9 r13
muli r0 r9 1999744
divi0 1000000
sub0 r8
mov r10 r0
imm r13 0
store r13 r9
imm r13 1
store r13 r10

; Ball 1 y oscillator.
imm r13 2
load r8 r13
imm r13 3
load r9 r13
muli r0 r9 1999900
divi0 1000000
sub0 r8
mov r10 r0
imm r13 2
store r13 r9
imm r13 3
store r13 r10

; Ball 2 x oscillator.
imm r13 4
load r8 r13
imm r13 5
load r9 r13
muli r0 r9 1998976
divi0 1000000
sub0 r8
mov r10 r0
imm r13 4
store r13 r9
imm r13 5
store r13 r10

; Ball 2 y oscillator.
imm r13 6
load r8 r13
imm r13 7
load r9 r13
muli r0 r9 1999600
divi0 1000000
sub0 r8
mov r10 r0
imm r13 6
store r13 r9
imm r13 7
store r13 r10

; Ball 3 x oscillator.
imm r13 8
load r8 r13
imm r13 9
load r9 r13
muli r0 r9 1997696
divi0 1000000
sub0 r8
mov r10 r0
imm r13 8
store r13 r9
imm r13 9
store r13 r10

; Ball 3 y oscillator.
imm r13 10
load r8 r13
imm r13 11
load r9 r13
muli r0 r9 1999100
divi0 1000000
sub0 r8
mov r10 r0
imm r13 10
store r13 r9
imm r13 11
store r13 r10

jmp frame
