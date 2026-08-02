.screen 64 64

; Multicolor radial XOR
;
; The four second-order oscillators complete 3, 5, 4, and 5 turns in
; 960 frames. The color phase also repeats there, producing a clean loop.
; Oscillator states use a scale of 100,000,000.
;
; r2  frame
; r3  x1                r10 rows left
; r4  y1                r11 distance 1
; r5  x2                r12 distance 2
; r6  y2                r13 temporary
; r7  x                 r14 square-root estimate
; r8  y                 r15 temporary / color
; r9  pixels
; r16-r23                oscillator (previous, current) pairs

; Preserve each oscillator as a (previous, current) register pair.
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
mov r11 r14

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
mov r12 r14

; pattern = (d1 XOR d2) >> 3. Odd bands are black; even bands
; cycle through colors 10..15, advancing once every ten frames.
mov r0 r11
xor0 r12
divi0 8
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

inc r7
dec r9
jc r9 pixel

inc r8
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
