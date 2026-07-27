.screen

; Draw one Bresenham line per round on the 32x24 display.
; The processor blocks on the next read after the final round.
;
; During setup:
;   r2 x0, r3 y0; x1 and y1 pass directly through r0
; During drawing:
;   r2 display address   r3 branch error
;   r4 scaled pixels remaining
; Shared:
;   r5 abs(x1-x0)       r6 x address step
;   r7 signed dy        r8 y address step
; r1 remains 15 while drawing and supplies both the color and counter step.

next_round:
read r2
read r3
read r0
sub0 r2
mov r5 r0

jc r0 dx_positive
imm r6 -1
neg r5
jmp dx_done
dx_positive:
imm r6 1
dx_done:

read r0
sub0 r3
mov r7 r0

jc r0 dy_positive
imm r8 -32
jmp dy_done
dy_positive:
imm r8 32
neg r7
dy_done:

mov r0 r3
muli0 32
add0 r2
mov r2 r0

; abs(dy) > dx selects the steep loop.
imm r0 0
sub0 r7
sub0 r5
jc r0 steep_init

; The shallow branch error is 2*err-dx = dx+2*dy.
mov r0 r5
add0 r7
add0 r7
mov r3 r0

mov r0 r5
addi0 1
muli0 15
mov r4 r0
shallow_loop:
screen_addr r2
screen_data r1

jc r3 shallow_skip_y
mov r0 r3
add0 r5
add0 r5
mov r3 r0
mov r0 r2
add0 r8
mov r2 r0
shallow_skip_y:

mov r0 r3
add0 r7
add0 r7
mov r3 r0
mov r0 r2
add0 r6
mov r2 r0

mov r0 r4
sub0 r1
mov r4 r0
jc r0 shallow_loop
jmp finish_round

steep_init:
; The steep branch error is dy-2*err = -2*dx-dy.
imm r0 0
sub0 r5
sub0 r5
sub0 r7
mov r3 r0

imm r0 1
sub0 r7
muli0 15
mov r4 r0
steep_loop:
screen_addr r2
screen_data r1

jc r3 steep_skip_x
mov r0 r3
sub0 r7
sub0 r7
mov r3 r0
mov r0 r2
add0 r6
mov r2 r0
steep_skip_x:

mov r0 r3
sub0 r5
sub0 r5
mov r3 r0
mov r0 r2
add0 r8
mov r2 r0

mov r0 r4
sub0 r1
mov r4 r0
jc r0 steep_loop

finish_round:
screen_swap r0
jmp next_round
