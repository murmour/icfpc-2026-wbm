.screen 64 64

; Rotating, breathing polar grid based on demoserv/effect_spiral.c.
;
; atan2 is approximated by a 40-sector diamond angle:
;     quarter_angle = 10 * abs(dy) / (abs(dx) + abs(dy))
; Distance is approximated by max(abs(dx), abs(dy)) +
; 3/8 * min(abs(dx), abs(dy)). Radial boundaries retain the source's
; 3.0 initial spacing and 1.08 exponential growth.
;
; r2,r3   center oscillator sine, cosine (scale 1,000,000)
; r4,r5   moving center x,y
; r6      palette phase
; r7      palette phase frame counter
; r8,r9   pixel x,y
; r10,r11 row/pixel counters
; r12,r13 pixel deltas / radial state
; r14     angular sector / color
; r15     temporary

imm r2 0
imm r3 1000000
imm r6 0
imm r7 5

frame:
; rr = 25 + 5*cos(frame), with the source's negative frame direction.
muli r15 r3 5
divi r15 r15 1000000
addi r15 r15 25

; center_x = 32 + rr*cos(frame)
mul r4 r15 r3
divi r4 r4 1000000
addi r4 r4 32

; center_y = 32 + rr*sin(frame)
mul r5 r15 r2
divi r5 r5 1000000
addi r5 r5 32

imm r9 0
imm r10 64

row:
imm r8 0
imm r11 64

pixel:
sub r12 r8 r4
sub r13 r9 r5

; Split by quadrant while converting both deltas to absolute values.
mov r15 r12
addi r15 r15 1
jc r15 dx_nonnegative

; dx < 0
neg r12
mov r15 r13
addi r15 r15 1
jc r15 quadrant_2

; Quadrant 3: sector = 20 + q.
neg r13
muli r14 r13 10
add r15 r12 r13
div r14 r14 r15
addi r14 r14 20
jmp angle_ready

quadrant_2:
; Quadrant 2: sector = 20 - q.
muli r14 r13 10
add r15 r12 r13
div r14 r14 r15
imm r15 20
sub r14 r15 r14
jmp angle_ready

dx_nonnegative:
mov r15 r13
addi r15 r15 1
jc r15 quadrant_1

; Quadrant 4: sector = 40 - q, with the positive x axis mapped to zero.
neg r13
muli r14 r13 10
add r15 r12 r13
div r14 r14 r15
jc r14 quadrant_4_nonzero
imm r14 0
jmp angle_ready
quadrant_4_nonzero:
imm r15 40
sub r14 r15 r14
jmp angle_ready

quadrant_1:
; Quadrant 1: sector = q. Handle the exact moving center separately.
add r15 r12 r13
jc r15 quadrant_1_nonzero
imm r14 0
jmp angle_ready
quadrant_1_nonzero:
muli r14 r13 10
div r14 r14 r15

angle_ready:
; Approximate hypot(dx,dy) and scale it by 100 for radial boundaries.
sub r15 r12 r13
jc r15 dx_is_larger

; dy >= dx
muli r15 r12 3
divi r15 r15 8
add r12 r13 r15
jmp distance_ready

dx_is_larger:
muli r15 r13 3
divi r15 r15 8
add r12 r12 r15

distance_ready:
muli r12 r12 100

; Count exponentially widening rings directly into the color index.
imm r13 0
imm r15 300
radial_loop:
sub r0 r12 r13
jc r0 radial_advance
jmp radial_ready

radial_advance:
add r13 r13 r15
muli r15 r15 108
divi r15 r15 100
inc r14
jmp radial_loop

radial_ready:
add r14 r14 r6

; color_index %= 11
color_reduce:
subi r0 r14 10
jc r0 color_subtract
jmp color_ready
color_subtract:
subi r14 r14 11
jmp color_reduce

color_ready:
; Palette indices 0..8 map to C64 colors 2..10. The last two map to
; LightGreen (13) and LightBlue (14).
addi r14 r14 2
subi r0 r14 10
jc r0 palette_high
jmp emit
palette_high:
addi r14 r14 2

emit:
screen_data r14

inc r8
dec r11
jc r11 pixel

inc r9
dec r10
jc r10 row

imm r0 0
screen_swap r0

; Rotate the moving center by -1 degree.
muli r12 r2 999848
muli r13 r3 17452
sub r12 r12 r13
divi r12 r12 1000000

muli r13 r3 999848
muli r15 r2 17452
add r13 r13 r15
divi r13 r13 1000000

mov r2 r12
mov r3 r13

; The source advances its palette by -1 every five frames.
dec r7
jc r7 frame
imm r7 5
dec r6
addi r0 r6 1
jc r0 frame
imm r6 10
jmp frame
