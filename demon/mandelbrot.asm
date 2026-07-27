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
mul r5 r13 r3
divi r5 r5 64
addi r5 r5 3120562

imm r12 -32
imm r14 64

pixel:
; c_re = x*scale/64 - 0.745.
mul r4 r12 r3
divi r4 r4 64
addi r4 r4 -12499026

imm r6 0
imm r7 0
imm r11 0

iterate:
mul r8 r6 r6
mul r9 r7 r7

; Stop when |z| squared is at least 4.0.
add r10 r8 r9
subi r10 r10 1125899906842623
jc r10 escaped

; z_re = z_re^2 - z_im^2 + c_re.
sub r8 r8 r9
divi r8 r8 16777216
add r8 r8 r4

; z_im = 2*z_re*z_im + c_im, using the old components.
mul r9 r6 r7
muli r9 r9 2
divi r9 r9 16777216
add r9 r9 r5

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
divi r8 r10 15
muli r8 r8 15
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
muli r3 r3 98
divi r3 r3 100
inc r2
jmp frame
