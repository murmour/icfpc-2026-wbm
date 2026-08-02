.screen 64 64
.memory 56

; Rotating four-dimensional hypercube (tesseract).
;
; Memory:
;   0..31   sixteen projected (x,y) pairs
;   32..47  projected vertex depths
;   48..55  (sin,cos) oscillator pairs for XW, YZ, ZW, and XY
;
; r2-r5    vertex x,y,z,w
; r6       vertex / edge index
; r7-r15   projection and line-rendering temporaries
;
; Vertex coordinates use a scale of 3584. This preserves fractional motion
; through all four rotations while making 0.35*w exactly match the projected
; depth scale of 10240.

; All four rotations begin at zero.
imm r12 48
imm r13 0
imm r14 1000000000
store r12 r13
inc r12
store r12 r14
inc r12
store r12 r13
inc r12
store r12 r14
inc r12
store r12 r13
inc r12
store r12 r14
inc r12
store r12 r13
inc r12
store r12 r14

frame:
; Project all sixteen vertices.
imm r6 0

project_vertex:
; Decode the four coordinate signs from the vertex index.
mov r0 r6
andi0 1
jc r0 vertex_x_positive
imm r2 -3584
jmp vertex_x_ready
vertex_x_positive:
imm r2 3584
vertex_x_ready:

mov r0 r6
andi0 2
jc r0 vertex_y_positive
imm r3 -3584
jmp vertex_y_ready
vertex_y_positive:
imm r3 3584
vertex_y_ready:

mov r0 r6
andi0 4
jc r0 vertex_z_positive
imm r4 -3584
jmp vertex_z_ready
vertex_z_positive:
imm r4 3584
vertex_z_ready:

mov r0 r6
andi0 8
jc r0 vertex_w_positive
imm r5 -3584
jmp vertex_w_ready
vertex_w_positive:
imm r5 3584
vertex_w_ready:

; Rotate XW.
imm r12 48
load r13 r12
inc r12
load r14 r12
mul r7 r2 r14
mul r8 r5 r13
sub r0 r7 r8
divi0 1000000000
mov r7 r0
mul r8 r2 r13
mul r9 r5 r14
add r0 r8 r9
divi0 1000000000
mov r8 r0
mov r2 r7
mov r5 r8

; Rotate YZ.
imm r12 50
load r13 r12
inc r12
load r14 r12
mul r7 r3 r14
mul r8 r4 r13
sub r0 r7 r8
divi0 1000000000
mov r7 r0
mul r8 r3 r13
mul r9 r4 r14
add r0 r8 r9
divi0 1000000000
mov r8 r0
mov r3 r7
mov r4 r8

; Rotate ZW.
imm r12 52
load r13 r12
inc r12
load r14 r12
mul r7 r4 r14
mul r8 r5 r13
sub r0 r7 r8
divi0 1000000000
mov r7 r0
mul r8 r4 r13
mul r9 r5 r14
add r0 r8 r9
divi0 1000000000
mov r8 r0
mov r4 r7
mov r5 r8

; Rotate XY.
imm r12 54
load r13 r12
inc r12
load r14 r12
mul r7 r2 r14
mul r8 r3 r13
sub r0 r7 r8
divi0 1000000000
mov r7 r0
mul r8 r2 r13
mul r9 r3 r14
add r0 r8 r9
divi0 1000000000
mov r8 r0
mov r2 r7
mov r3 r8

; 4D perspective. r7-r9 retain x,y,z at a scale of 10240.
imm r13 11469
sub r13 r13 r5
muli r0 r2 21504
div0 r13
mov r7 r0
muli r0 r3 21504
div0 r13
mov r8 r0
muli r0 r4 21504
div0 r13
mov r9 r0

; 3D perspective.
imm r13 46080
sub r13 r13 r9
muli r0 r7 55
div0 r13
addi0 32
mov r10 r0
muli r0 r8 55
div0 r13
addi0 32
mov r11 r0

; Clamp projected endpoints because the physical screen-address port does
; not clip lines for us.
jc r10 project_x_nonnegative
imm r10 0
jmp project_x_ready
project_x_nonnegative:
subi r0 r10 63
jc r0 project_x_high
jmp project_x_ready
project_x_high:
imm r10 63
project_x_ready:

jc r11 project_y_nonnegative
imm r11 0
jmp project_y_ready
project_y_nonnegative:
subi r0 r11 63
jc r0 project_y_high
jmp project_y_ready
project_y_high:
imm r11 63
project_y_ready:

; Store projected x,y and depth.
muli r12 r6 2
store r12 r10
inc r12
store r12 r11
addi r12 r6 32
add r13 r5 r9
store r12 r13

inc r6
subi r0 r6 15
jc r0 projection_done
jmp project_vertex

projection_done:
; Clear the back buffer.
imm r7 0
screen_addr r7
imm r8 4096
clear_pixel:
screen_data r7
dec r8
jc r8 clear_pixel

; Each group of eight edges belongs to one coordinate dimension.
imm r6 0

select_edge:
divi r12 r6 8
muli r13 r12 8
sub r13 r6 r13

; Insert a zero bit into the three-bit edge slot to obtain endpoint A.
jc r12 edge_dimension_nonzero
muli r13 r13 2
addi r14 r13 1
jmp edge_ready
edge_dimension_nonzero:
subi r0 r12 1
jc r0 edge_dimension_2_or_3

; Dimension 1.
mov r0 r13
andi0 1
mov r14 r0
divi r0 r13 2
muli0 4
add0 r14
mov r13 r0
addi r14 r13 2
jmp edge_ready

edge_dimension_2_or_3:
subi r0 r12 2
jc r0 edge_dimension_3

; Dimension 2.
mov r0 r13
andi0 3
mov r14 r0
divi r0 r13 4
muli0 8
add0 r14
mov r13 r0
addi r14 r13 4
jmp edge_ready

edge_dimension_3:
addi r14 r13 8

edge_ready:
; Average endpoint depth chooses far, middle, or near colors.
addi r11 r13 32
load r15 r11
addi r11 r14 32
load r10 r11
add r15 r15 r10
subi r0 r15 11264
jc r0 edge_color_near
addi r0 r15 7168
jc r0 edge_color_middle

; Far palette: Blue, Green, Red, Brown.
jc r12 edge_far_nonzero
imm r15 6
jmp edge_color_ready
edge_far_nonzero:
subi r0 r12 1
jc r0 edge_far_2_or_3
imm r15 5
jmp edge_color_ready
edge_far_2_or_3:
subi r0 r12 2
jc r0 edge_far_3
imm r15 2
jmp edge_color_ready
edge_far_3:
imm r15 9
jmp edge_color_ready

edge_color_middle:
; Middle palette: LightBlue, LightGreen, LightRed, Orange.
jc r12 edge_middle_nonzero
imm r15 14
jmp edge_color_ready
edge_middle_nonzero:
subi r0 r12 1
jc r0 edge_middle_2_or_3
imm r15 13
jmp edge_color_ready
edge_middle_2_or_3:
subi r0 r12 2
jc r0 edge_middle_3
imm r15 10
jmp edge_color_ready
edge_middle_3:
imm r15 8
jmp edge_color_ready

edge_color_near:
; Near palette: Cyan, Yellow, White, LightGray.
jc r12 edge_near_nonzero
imm r15 3
jmp edge_color_ready
edge_near_nonzero:
subi r0 r12 1
jc r0 edge_near_2_or_3
imm r15 7
jmp edge_color_ready
edge_near_2_or_3:
subi r0 r12 2
jc r0 edge_near_3
imm r15 1
jmp edge_color_ready
edge_near_3:
imm r15 15

edge_color_ready:
; Load x0,y0,x1,y1 into r7..r10.
muli r11 r13 2
load r7 r11
inc r11
load r8 r11
muli r11 r14 2
load r9 r11
inc r11
load r10 r11

; Fixed-point DDA.
sub r9 r9 r7
sub r10 r10 r8
mov r11 r9
jc r11 edge_abs_dx_ready
neg r11
edge_abs_dx_ready:
mov r12 r10
jc r12 edge_abs_dy_ready
neg r12
edge_abs_dy_ready:
sub r0 r11 r12
jc r0 edge_steps_ready
mov r11 r12
edge_steps_ready:
jc r11 edge_steps_nonzero
imm r11 1
edge_steps_nonzero:

muli r7 r7 1024
muli r8 r8 1024
muli r0 r9 1024
div0 r11
mov r9 r0
muli r0 r10 1024
div0 r11
mov r10 r0
inc r11

draw_edge_pixel:
divi r0 r8 1024
muli0 64
mov r12 r0
divi r13 r7 1024
add r12 r12 r13
screen_addr r12
screen_data r15
add r7 r7 r9
add r8 r8 r10
dec r11
jc r11 draw_edge_pixel

inc r6
subi r0 r6 31
jc r0 hypercube_ready
jmp select_edge

hypercube_ready:
imm r0 0
screen_swap r0

; Advance XW by 0.017 radians.
imm r12 48
load r7 r12
inc r12
load r8 r12
muli r9 r7 999855503
muli r10 r8 16999181
add r0 r9 r10
divi0 1000000000
mov r9 r0
muli r10 r8 999855503
muli r11 r7 16999181
sub r0 r10 r11
divi0 1000000000
mov r10 r0
imm r12 48
store r12 r9
inc r12
store r12 r10

; Advance YZ by 0.013 radians.
imm r12 50
load r7 r12
inc r12
load r8 r12
muli r9 r7 999915501
muli r10 r8 12999634
add r0 r9 r10
divi0 1000000000
mov r9 r0
muli r10 r8 999915501
muli r11 r7 12999634
sub r0 r10 r11
divi0 1000000000
mov r10 r0
imm r12 50
store r12 r9
inc r12
store r12 r10

; Advance ZW by 0.009 radians.
imm r12 52
load r7 r12
inc r12
load r8 r12
muli r9 r7 999959500
muli r10 r8 8999879
add r0 r9 r10
divi0 1000000000
mov r9 r0
muli r10 r8 999959500
muli r11 r7 8999879
sub r0 r10 r11
divi0 1000000000
mov r10 r0
imm r12 52
store r12 r9
inc r12
store r12 r10

; Advance XY by 0.006 radians.
imm r12 54
load r7 r12
inc r12
load r8 r12
muli r9 r7 999982000
muli r10 r8 5999964
add r0 r9 r10
divi0 1000000000
mov r9 r0
muli r10 r8 999982000
muli r11 r7 5999964
sub r0 r10 r11
divi0 1000000000
mov r10 r0
imm r12 54
store r12 r9
inc r12
store r12 r10

jmp frame
