.screen 64 64

; Four-sided scanline twister.
;
; The reference effect indexes a 512-entry table with:
;
;   roll + y * 1.2 * sin(14*pi*roll/512) * cos(2*pi*roll/512)
;
; We evaluate the same expression in fixed point, then approximate sine with
; x * (1800 - abs(x)) / 791. Angles are measured in tenths of a degree and
; sine values are scaled by 1024.
;
; r2      roll in half-index units (0..1021)
; r3      fixed-point row phase
; r4,r5   sine/cosine or projected positive vertices
; r6,r7   arithmetic temporaries or opposite vertices
; r8-r10  left, split, and right silhouette boundaries
; r11     pixel x
; r12     local face offset
; r13     rows left
; r14     fixed-point vertical phase step
; r15     face width

; Start near a maximum bend so the first frame is already visibly twisted.
imm r2 40

frame:
; sin(14*pi*roll/512): angle = roll * 1575/32 tenths of a degree.
divi r0 r2 2
muli0 1575
divi0 32
mov r3 r0

high_wrap:
subi r0 r3 1799
jc r0 high_subtract_turn
jmp high_ready

high_subtract_turn:
subi r3 r3 3600
jmp high_wrap

high_ready:
mov r4 r3
mov r5 r3
jc r5 high_abs_ready
neg r5

high_abs_ready:
imm r6 1800
sub r6 r6 r5
mul r0 r4 r6
divi0 791
mov r4 r0

; cos(2*pi*roll/512) = sin(roll * 225/32 + 90 degrees).
divi r0 r2 2
muli0 225
divi0 32
addi0 900
mov r3 r0

low_wrap:
subi r0 r3 1799
jc r0 low_subtract_turn
jmp low_ready

low_subtract_turn:
subi r3 r3 3600
jmp low_wrap

low_ready:
mov r5 r3
mov r6 r3
jc r6 low_abs_ready
neg r6

low_abs_ready:
imm r7 1800
sub r7 r7 r6
mul r0 r5 r7
divi0 791
mov r5 r0

; r14 is 1.2*sin(high)*cos(low), scaled by 1024.
mul r0 r4 r5
muli0 12
divi0 10240
mov r14 r0

divi r0 r2 2
muli0 1024
mov r3 r0
imm r13 64

row:
; Convert the fixed-point phase to the reference's truncation toward zero.
mov r6 r3
jc r6 row_phase_positive
addi r6 r6 1023

row_phase_positive:
divi r6 r6 1024

; Wrap the table index into 0..511.
wouaf_lower:
jc r6 wouaf_upper
addi r6 r6 512
jmp wouaf_upper

wouaf_subtract:
subi r6 r6 512

wouaf_upper:
subi r0 r6 511
jc r0 wouaf_subtract

; theta = 3*pi*wouaf/512 = wouaf * 675/64 tenths of a degree.
muli r0 r6 675
divi0 64
mov r7 r0
subi0 1799
jc r0 theta_subtract_turn
jmp theta_ready

theta_subtract_turn:
subi r7 r7 3600

theta_ready:
; r4 = sin(theta).
mov r4 r7
mov r5 r7
jc r5 theta_abs_ready
neg r5

theta_abs_ready:
imm r6 1800
sub r6 r6 r5
mul r0 r4 r6
divi0 791
mov r4 r0

; r5 = cos(theta) = sin(theta + 90 degrees).
addi r7 r7 900
subi0 1799
jc r0 cosine_subtract_turn
jmp cosine_ready

cosine_subtract_turn:
subi r7 r7 3600

cosine_ready:
mov r5 r7
mov r6 r7
jc r6 cosine_abs_ready
neg r6

cosine_abs_ready:
imm r7 1800
sub r7 r7 r6
mul r0 r5 r7
divi0 791
mov r5 r0

; Project the square's four vertices around x=32 with radius 28.
muli r0 r4 28
divi0 1024
addi0 32
mov r4 r0
imm r6 64
sub r6 r6 r4

muli r0 r5 28
divi0 1024
addi0 32
mov r5 r0
imm r7 64
sub r7 r7 r5

; Choose the leftmost vertex and the next two cyclic vertices.
; They are the left edge, the face, and the right edge of the visible half of the square.
subi r0 r4 32
jc r0 sine_positive
subi r0 r5 32
jc r0 quadrant_4

; Both sine and cosine are non-positive.
sub r0 r4 r5
jc r0 front_2
jmp front_1

quadrant_4:
; cosine > -sine
add r0 r4 r5
subi0 64
jc r0 front_0
jmp front_1

sine_positive:
subi r0 r5 32
jc r0 quadrant_1

; sine > -cosine
add r0 r4 r5
subi0 64
jc r0 front_3
jmp front_2

quadrant_1:
; cosine > sine
sub r0 r5 r4
jc r0 front_0
jmp front_3

front_0:
mov r8 r7
mov r9 r4
mov r10 r5
jmp draw_row

front_1:
mov r8 r4
mov r9 r5
mov r10 r6
jmp draw_row

front_2:
mov r8 r5
mov r9 r6
mov r10 r7
jmp draw_row

front_3:
mov r8 r6
mov r9 r7
mov r10 r4

draw_row:
imm r11 0

pixel:
; Black outside the silhouette.
sub r0 r11 r8
addi0 1
jc r0 after_left
imm r0 0
jmp emit

after_left:
sub r0 r10 r11
addi0 1
jc r0 inside
imm r0 0
jmp emit

inside:
; Express x relative to either visible face.
sub r0 r9 r11
jc r0 first_face
sub r12 r11 r9
sub r15 r10 r9
jmp shade

first_face:
sub r12 r11 r8
sub r15 r9 r8

shade:
; Reproduce twister_zoom's four equal color bands.
divi r0 r15 4
sub0 r12
jc r0 color_red

divi r0 r15 2
sub0 r12
jc r0 color_green

divi r6 r15 4
divi r0 r15 2
add0 r6
sub0 r12
jc r0 color_yellow

imm r0 3
jmp emit

color_red:
imm r0 2
jmp emit

color_green:
imm r0 5
jmp emit

color_yellow:
imm r0 7

emit:
screen_data r0
inc r11
subi r0 r11 63
jc r0 row_done
jmp pixel

row_done:
add r3 r3 r14
dec r13
jc r13 row

imm r0 0
screen_swap r0

; Three half-index steps are 1.5 table entries (to slow down).
addi r2 r2 3
subi0 1021
jc r0 roll_wrap
jmp frame
roll_wrap:
subi r2 r2 1022
jmp frame
