.screen 64 64
.memory 17

; Fixed-point rotozoomed checkerboard using 16 registers.
;
; r2  phase             r9  pixels left
; r3  du/dx             r10 rows left
; r4  dv/dx             r11 sine/quotient
; r5  row u             r12 cosine/product
; r6  row v             r13 zoom/u remainder
; r7  pixel u           r14 temporary/v remainder
; r8  pixel v           r15 color

; Initialize the 17-entry quarter-wave sine table.
imm r2 0
imm r4 0
imm r5 0
store r4 r5
imm r4 1
imm r5 100
store r4 r5
imm r4 2
imm r5 200
store r4 r5
imm r4 3
imm r5 297
store r4 r5
imm r4 4
imm r5 392
store r4 r5
imm r4 5
imm r5 483
store r4 r5
imm r4 6
imm r5 569
store r4 r5
imm r4 7
imm r5 650
store r4 r5
imm r4 8
imm r5 724
store r4 r5
imm r4 9
imm r5 792
store r4 r5
imm r4 10
imm r5 851
store r4 r5
imm r4 11
imm r5 903
store r4 r5
imm r4 12
imm r5 946
store r4 r5
imm r4 13
imm r5 980
store r4 r5
imm r4 14
imm r5 1004
store r4 r5
imm r4 15
imm r5 1019
store r4 r5
imm r4 16
imm r5 1024
store r4 r5

frame:
; r11 = sin(phase). r3 is the quadrant, r4 the table offset, and
; r5 a temporary.
divi r3 r2 16
muli r5 r3 16
sub r4 r2 r5
jeq r3 1 sin_mirror
jeq r3 3 sin_mirror
jmp sin_lookup
sin_mirror:
imm r0 16
mov r1 r4
sub0 r1
mov r4 r0
sin_lookup:
load r11 r4
subi r0 r3 1
jc r0 sin_negate
jmp sin_done
sin_negate:
neg r11
sin_done:

; r12 = cos(phase) = sin(phase + 16).
addi r6 r2 16
subi r0 r6 63
jc r0 wrap_cos
jmp cos_phase_ready
wrap_cos:
subi r6 r6 64
cos_phase_ready:
divi r3 r6 16
muli r5 r3 16
sub r4 r6 r5
jeq r3 1 cos_mirror
jeq r3 3 cos_mirror
jmp cos_lookup
cos_mirror:
imm r0 16
mov r1 r4
sub0 r1
mov r4 r0
cos_lookup:
load r12 r4
subi r0 r3 1
jc r0 cos_negate
jmp cos_done
cos_negate:
neg r12
cos_done:

; Apply a small sinusoidal zoom and build the affine increments.
divi r0 r11 4
addi0 1024
mov r13 r0
mul r14 r12 r13
divi r3 r14 1024
mul r14 r11 r13
divi r4 r14 1024

; Start at the transformed upper-left corner.
sub r14 r3 r4
muli r5 r14 32
neg r5
add r14 r4 r3
muli r6 r14 32
neg r6
imm r10 64

row:
mov r7 r5
mov r8 r6
imm r9 64

pixel:
; Reduce u and v modulo 16384 without a dedicated remainder operation.
divi r11 r7 16384
muli r12 r11 16384
sub r13 r7 r12
divi r11 r8 16384
muli r12 r11 16384
sub r14 r8 r12

; XOR the high half-period bits to form the checkerboard.
subi r0 r13 8191
jc r0 u_high
subi r0 r14 8191
jc r0 light
jmp dark
u_high:
subi r0 r14 8191
jc r0 dark
jmp light

light:
imm r15 14
jmp emit
dark:
imm r15 2
emit:
screen_data r15

add r7 r7 r3
add r8 r8 r4
dec r9
jc r9 pixel

sub r5 r5 r4
add r6 r6 r3
dec r10
jc r10 row

imm r15 0
screen_swap r15
inc r2
subi r0 r2 63
jc r0 wrap_phase
jmp frame
wrap_phase:
subi r2 r2 64
jmp frame
