.screen 64 64

; Four-wave plasma based on demoserv/effect_plasma.c.
;
; Angles use tenths of a degree. Sine uses the signed parabolic
; approximation x * (1800 - abs(x)) / 791, producing values near
; [-1024, 1024]. Hypot uses max(abs(dx), abs(dy)) +
; 3/8 * min(abs(dx), abs(dy)).
;
; r2      frame phase in half-degree steps
; r3,r4   pixel x,y
; r5,r6   row/pixel counters
; r7      sum of four waves
; r8-r10  angle and sine temporaries
; r11-r13 distance temporaries
; r14,r15 temporaries / color

imm r2 0

frame:
imm r4 0
imm r5 64

row:
imm r3 0
imm r6 64

pixel:
imm r7 0

; sin(x*0.8 + frame*2.0)
muli r8 r3 8
muli r9 r2 4
add r8 r8 r9

wave1_upper:
subi r0 r8 1799
jc r0 wave1_subtract_turn
jmp wave1_lower
wave1_subtract_turn:
subi r8 r8 3600
jmp wave1_upper
wave1_lower:
imm r0 -1800
sub0 r8
jc r0 wave1_add_turn
jmp wave1_sine
wave1_add_turn:
addi r8 r8 3600
jmp wave1_lower

wave1_sine:
mov r9 r8
jc r9 wave1_abs_ready
neg r9
wave1_abs_ready:
imm r10 1800
sub r0 r10 r9
mul0 r8
divi0 791
mov r10 r0
add r7 r7 r10

; sin(y*0.5 - frame*1.5)
muli r8 r4 5
muli r9 r2 3
sub r8 r8 r9

wave2_upper:
subi r0 r8 1799
jc r0 wave2_subtract_turn
jmp wave2_lower
wave2_subtract_turn:
subi r8 r8 3600
jmp wave2_upper
wave2_lower:
imm r0 -1800
sub0 r8
jc r0 wave2_add_turn
jmp wave2_sine
wave2_add_turn:
addi r8 r8 3600
jmp wave2_lower

wave2_sine:
mov r9 r8
jc r9 wave2_abs_ready
neg r9
wave2_abs_ready:
imm r10 1800
sub r0 r10 r9
mul0 r8
divi0 791
mov r10 r0
add r7 r7 r10

; sin((x+y)*0.4 + frame*1.0)
add r0 r3 r4
muli0 4
mov r8 r0
muli r9 r2 2
add r8 r8 r9

wave3_upper:
subi r0 r8 1799
jc r0 wave3_subtract_turn
jmp wave3_lower
wave3_subtract_turn:
subi r8 r8 3600
jmp wave3_upper
wave3_lower:
imm r0 -1800
sub0 r8
jc r0 wave3_add_turn
jmp wave3_sine
wave3_add_turn:
addi r8 r8 3600
jmp wave3_lower

wave3_sine:
mov r9 r8
jc r9 wave3_abs_ready
neg r9
wave3_abs_ready:
imm r10 1800
sub r0 r10 r9
mul0 r8
divi0 791
mov r10 r0
add r7 r7 r10

; Approximate hypot(x-32, y-32).
subi r11 r3 32
jc r11 distance_dx_ready
neg r11
distance_dx_ready:
subi r12 r4 32
jc r12 distance_dy_ready
neg r12
distance_dy_ready:

sub r0 r11 r12
jc r0 distance_dx_larger

; abs(dy) >= abs(dx)
muli r0 r11 3
divi0 8
mov r13 r0
add r13 r12 r13
jmp distance_ready

distance_dx_larger:
muli r0 r12 3
divi0 8
mov r13 r0
add r13 r11 r13

distance_ready:
; sin(distance*0.3 - frame*0.5)
muli r0 r13 3
sub0 r2
mov r8 r0

wave4_upper:
subi r0 r8 1799
jc r0 wave4_subtract_turn
jmp wave4_lower
wave4_subtract_turn:
subi r8 r8 3600
jmp wave4_upper
wave4_lower:
imm r0 -1800
sub0 r8
jc r0 wave4_add_turn
jmp wave4_sine
wave4_add_turn:
addi r8 r8 3600
jmp wave4_lower

wave4_sine:
mov r9 r8
jc r9 wave4_abs_ready
neg r9
wave4_abs_ready:
imm r10 1800
sub r0 r10 r9
mul0 r8
divi0 791
mov r10 r0
add r7 r7 r10

; Original mapping: ((value + 4.0) * 2.0) % 16.
addi r0 r7 4096
divi0 512
mov r15 r0
subi r14 r15 15
jc r14 color_wrap
jmp emit
color_wrap:
subi r15 r15 16

emit:
screen_data r15

inc r3
dec r6
jc r6 pixel

inc r4
dec r5
jc r5 row

imm r0 0
screen_swap r0

; One frame is 0.5 degrees in the shared phase. It yields the source's
; +2.0, -1.5, +1.0, and -0.5 degree wave velocities.
addi r2 r2 5
subi r0 r2 3599
jc r0 phase_wrap
jmp frame
phase_wrap:
subi r2 r2 3600
jmp frame
