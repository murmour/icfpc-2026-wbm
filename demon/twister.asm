.screen 64 64

; Four-sided projected twister.
;
; r2,r3   sine, cosine   r8-r10 left, split, right
; r4-r7   projected x    r11    pixel x
; r12     pixels left    r13    rows left
; r14,r15 face colors

imm r2 0
imm r3 1000000

frame:
imm r13 64

row:
; Project the square's four vertices onto the horizontal axis.
muli r4 r2 18
divi r4 r4 1000000
addi r4 r4 32
imm r6 64
sub r6 r6 r4

muli r5 r3 18
divi r5 r5 1000000
addi r5 r5 32
imm r7 64
sub r7 r7 r5

; Select the front vertex from the signs and relative magnitudes of sin/cos.
jc r2 sine_positive
jc r3 quadrant_4

; Quadrant 3: front is vertex 2 when sin > cos, otherwise vertex 1.
sub r0 r2 r3
jc r0 front_2
jmp front_1

quadrant_4:
; Front is vertex 0 when cos > -sin, otherwise vertex 1.
add r0 r3 r2
jc r0 front_0
jmp front_1

sine_positive:
jc r3 quadrant_1

; Quadrant 2: front is vertex 3 when sin > -cos, otherwise vertex 2.
add r0 r2 r3
jc r0 front_3
jmp front_2

quadrant_1:
; Front is vertex 0 when cos > sin, otherwise vertex 3.
sub r0 r3 r2
jc r0 front_0
jmp front_3

front_0:
mov r8 r7
mov r9 r4
mov r10 r5
imm r14 3
imm r15 2
jmp draw_row

front_1:
mov r8 r4
mov r9 r5
mov r10 r6
imm r14 2
imm r15 4
jmp draw_row

front_2:
mov r8 r5
mov r9 r6
mov r10 r7
imm r14 4
imm r15 6
jmp draw_row

front_3:
mov r8 r6
mov r9 r7
mov r10 r4
imm r14 6
imm r15 3

draw_row:
imm r11 0
imm r12 64

pixel:
; Reject pixels left of the silhouette.
sub r0 r11 r8
addi r0 r0 1
jc r0 after_left
imm r0 0
jmp emit

after_left:
; Reject pixels right of the silhouette.
sub r0 r10 r11
addi r0 r0 1
jc r0 inside
imm r0 0
jmp emit

inside:
; The projected front vertex separates the two visible faces.
sub r0 r9 r11
jc r0 left_face
mov r0 r15
jmp emit

left_face:
mov r0 r14

emit:
screen_data r0
inc r11
dec r12
jc r12 pixel

; Advance the cross-section by 0.16 radians for the next scanline.
muli r4 r2 987227
muli r5 r3 159318
add r4 r4 r5
divi r4 r4 1000000

muli r5 r3 987227
muli r6 r2 159318
sub r5 r5 r6
divi r5 r5 1000000

mov r2 r4
mov r3 r5
dec r13
jc r13 row

imm r0 0
screen_swap r0

; Undo the 64 row rotations and advance the next frame by 0.06 radians.
muli r4 r2 -728119
muli r5 r3 685450
add r4 r4 r5
divi r4 r4 1000000

muli r5 r3 -728119
muli r6 r2 685450
sub r5 r5 r6
divi r5 r5 1000000

mov r2 r4
mov r3 r5
jmp frame
