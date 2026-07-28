.screen 64 64

; Animated Mandelbrot zoom based on demoserv/effect_mandelbrot.c.
; Complex coordinates use Q24 fixed point (16777216 units per real unit).
;
; r2  frame             r9  z_im squared / temporary
; r3  scale             r10 temporary / color
; r4  c_re              r11 iteration
; r5  c_im              r12 x coordinate
; r6  z_re              r13 y coordinate
; r7  z_im              r14 pixels left
; r8  z_re squared      r15 rows left

imm r2 0
imm r3 16777216

frame:
imm r13 -32
imm r15 64

row:
; c_im = y*scale/64 + 0.186.
mul r0 r13 r3
divi0 64
addi0 3120562
mov r5 r0

imm r12 -32
imm r14 64

pixel:
; c_re = x*scale/64 - 0.745.
mul r0 r12 r3
divi0 64
addi0 -12499026
mov r4 r0

imm r6 0
imm r7 0
imm r11 0

iterate:
mul r8 r6 r6
mul r9 r7 r7

; Stop when |z| squared is at least 4.0.
add r0 r8 r9
subi0 1125899906842623
mov r10 r0
jc r10 escaped

; z_re = z_re^2 - z_im^2 + c_re.
sub r0 r8 r9
divi0 16777216
add0 r4
mov r8 r0

; z_im = 2*z_re*z_im + c_im, using the old components.
mul r0 r6 r7
muli0 2
divi0 16777216
add0 r5
mov r9 r0

mov r6 r8
mov r7 r9
inc r11
subi r10 r11 63
jc r10 bounded
jmp iterate

bounded:
imm r10 0
jmp emit

escaped:
; color = (iteration + frame/10) % 15 + 1.
divi r8 r2 10
add r10 r11 r8
divi r0 r10 15
muli0 15
mov r8 r0
sub r10 r10 r8
inc r10

emit:
screen_data r10

inc r12
dec r14
jc r14 pixel

inc r13
dec r15
jc r15 row

imm r10 0
screen_swap r10

; scale *= 0.98.
muli r0 r3 98
divi0 100
mov r3 r0
inc r2
jmp frame
