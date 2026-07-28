.screen 64 64
.memory 17

; Two moving radial fields based on demoserv/effect_xor.c.
;
; Four second-order oscillators implement the source's sin(time/2),
; sin(time/4), cos(time/3), and cos(time), with time advancing by 0.05.
; Oscillator states use a scale of 1,000,000.
;
; r3  x1                r10 rows left
; r4  y1                r11 distance 1
; r5  x2                r12 distance 2
; r6  y2                r13 temporary
; r7  x / address       r14 square-root estimate
; r8  y / state         r15 temporary / color
; r9  pixels / state

; Memory stores (previous, current) for each oscillator.
imm r7 0
imm r8 -24997
store r7 r8
imm r7 1
imm r8 0
store r7 r8

imm r7 2
imm r8 -12500
store r7 r8
imm r7 3
imm r8 0
store r7 r8

imm r7 4
imm r8 999861
store r7 r8
imm r7 5
imm r8 1000000
store r7 r8

imm r7 6
imm r8 998750
store r7 r8
imm r7 7
imm r8 1000000
store r7 r8

frame:
; Convert oscillator amplitudes to pixel centers:
; (64/3) / 1,000,000 = 1 / 46,875.
imm r7 1
load r3 r7
divi r0 r3 46875
addi0 32
mov r3 r0

imm r7 3
load r4 r7
divi r0 r4 46875
addi0 32
mov r4 r0

imm r7 5
load r5 r7
divi r0 r5 46875
addi0 32
mov r5 r0

imm r7 7
load r6 r7
divi r0 r6 46875
addi0 32
mov r6 r0

imm r8 0
imm r10 64

row:
imm r7 0
imm r9 64

pixel:
; d1 = floor(hypot(x - x1, y - y1)).
sub r11 r7 r3
jc r11 d1_dx_positive
neg r11
d1_dx_positive:
mul r11 r11 r11
sub r12 r8 r4
jc r12 d1_dy_positive
neg r12
d1_dy_positive:
mul r12 r12 r12
add r11 r11 r12

imm r14 64
imm r15 6
d1_sqrt:
div r0 r11 r14
add0 r14
mov r13 r0
divi r14 r13 2
dec r15
jc r15 d1_sqrt
mul r0 r14 r14
sub0 r11
mov r13 r0
jc r13 d1_adjust
jmp d1_ready
d1_adjust:
dec r14
d1_ready:
divi r11 r14 8

; d2 = floor(hypot(x - x2, y - y2)).
sub r12 r7 r5
jc r12 d2_dx_positive
neg r12
d2_dx_positive:
mul r12 r12 r12
sub r13 r8 r6
jc r13 d2_dy_positive
neg r13
d2_dy_positive:
mul r13 r13 r13
add r12 r12 r13

imm r14 64
imm r15 6
d2_sqrt:
div r0 r12 r14
add0 r14
mov r13 r0
divi r14 r13 2
dec r15
jc r15 d2_sqrt
mul r0 r14 r14
sub0 r12
mov r13 r0
jc r13 d2_adjust
jmp d2_ready
d2_adjust:
dec r14
d2_ready:
divi r12 r14 8

; Bit 3 of d1 XOR d2 selects cyan or black.
add r13 r11 r12
divi r0 r13 2
muli0 2
mov r14 r0
sub r0 r13 r14
muli0 3
mov r13 r0
imm r15 3
sub r15 r15 r13
screen_data r15

inc r7
dec r9
jc r9 pixel

inc r8
dec r10
jc r10 row

imm r15 0
screen_swap r15

; x1: w = 0.025, 2*cos(w) = 1.999375.
imm r7 0
load r8 r7
imm r7 1
load r9 r7
muli r0 r9 1999375
divi0 1000000
sub0 r8
mov r10 r0
imm r7 0
store r7 r9
imm r7 1
store r7 r10

; y1: w = 0.0125, 2*cos(w) = 1.999844.
imm r7 2
load r8 r7
imm r7 3
load r9 r7
muli r0 r9 1999844
divi0 1000000
sub0 r8
mov r10 r0
imm r7 2
store r7 r9
imm r7 3
store r7 r10

; x2: w = 1/60, 2*cos(w) = 1.999722.
imm r7 4
load r8 r7
imm r7 5
load r9 r7
muli r0 r9 1999722
divi0 1000000
sub0 r8
mov r10 r0
imm r7 4
store r7 r9
imm r7 5
store r7 r10

; y2: w = 0.05, 2*cos(w) = 1.997501.
imm r7 6
load r8 r7
imm r7 7
load r9 r7
muli r0 r9 1997501
divi0 1000000
sub0 r8
mov r10 r0
imm r7 6
store r7 r9
imm r7 7
store r7 r10

jmp frame
