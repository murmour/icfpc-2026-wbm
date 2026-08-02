.screen 64 64
.memory 24 48

; Depth-shaded perspective cube rotating around the X and Y axes.
;
; Eight projected (x,y) vertex pairs occupy memory slots 0..15.
; Camera-space vertex depths occupy memory slots 16..23.
; Vertices on each z face use cyclic order, allowing all twelve edges
; to be selected arithmetically and drawn by one fixed-point DDA loop.
;
; Geometry uses Q12 fixed point so successive rotations retain subpixel motion.
; r2,r3   sin/cos of Y rotation, scale 100,000,000
; r4,r5   sin/cos of X rotation, scale 100,000,000
; r6      vertex / edge index
; r7-r15  projection and line-rendering temporaries

imm r2 0
imm r3 100000000
imm r4 -34202014
imm r5 93969262

frame:
; Project all eight vertices.
imm r6 0

project_vertex:
; Reduce the vertex index to its cyclic face index and select z.
mov r14 r6
subi r0 r14 3
jc r0 vertex_back
imm r9 -61440
jmp vertex_z_ready
vertex_back:
subi r14 r14 4
imm r9 61440
vertex_z_ready:

; y is negative for cyclic vertices 0,1 and positive for 2,3.
subi r0 r14 1
jc r0 vertex_y_positive
imm r8 -61440
jmp vertex_y_ready
vertex_y_positive:
imm r8 61440
vertex_y_ready:

; x follows the cyclic pattern negative, positive, positive, negative.
mov r0 r14
jc r0 vertex_x_middle
imm r7 -61440
jmp vertex_x_ready
vertex_x_middle:
imm r0 3
sub0 r14
jc r0 vertex_x_positive
imm r7 -61440
jmp vertex_x_ready
vertex_x_positive:
imm r7 61440
vertex_x_ready:

; Rotate around Y:
;   x1 = x*cos_y + z*sin_y
;   z1 = z*cos_y - x*sin_y
mul r10 r7 r3
mul r15 r9 r2
add r0 r10 r15
divi0 100000000
mov r10 r0

mul r11 r9 r3
mul r15 r7 r2
sub r0 r11 r15
divi0 100000000
mov r11 r0

; Rotate around X:
;   y2 = y*cos_x - z1*sin_x
;   z2 = y*sin_x + z1*cos_x
mul r12 r8 r5
mul r15 r11 r4
sub r0 r12 r15
divi0 100000000
mov r12 r0

mul r13 r8 r4
mul r15 r11 r5
add r0 r13 r15
divi0 100000000
mov r13 r0

; Preserve camera-space depth for dynamic edge shading.
addi r14 r6 16
store r14 r13

; Perspective projection with camera distance 90.
addi r13 r13 368640
muli r0 r10 90
div0 r13
addi0 32
mov r10 r0

muli r0 r12 90
div0 r13
addi0 32
mov r12 r0

; Store projected x and y.
muli r14 r6 2
store r14 r10
inc r14
store r14 r12

inc r6
subi r0 r6 7
jc r0 projection_done
jmp project_vertex

projection_done:
; Clear the complete back buffer.
imm r7 0
screen_addr r7
imm r8 4096
clear_pixel:
screen_data r7
dec r8
jc r8 clear_pixel

; Edges 0..3 surround the first face, 4..7 surround the second,
; and 8..11 connect corresponding face vertices.
imm r6 0

select_edge:
subi r0 r6 7
jc r0 connector_edge
subi r0 r6 3
jc r0 back_face_edge

; First face: e -> e+1, with edge 3 wrapping to vertex 0.
mov r13 r6
addi r14 r6 1
subi r0 r6 2
jc r0 front_face_wrap
jmp load_edge
front_face_wrap:
imm r14 0
jmp load_edge

; Second face: e -> e+1, with edge 7 wrapping to vertex 4.
back_face_edge:
mov r13 r6
addi r14 r6 1
subi r0 r6 6
jc r0 back_face_wrap
jmp load_edge
back_face_wrap:
imm r14 4
jmp load_edge

; Connector e uses vertices e-8 and e-4.
connector_edge:
subi r13 r6 8
addi r14 r13 4

load_edge:
; An edge whose midpoint lies behind the origin uses dark gray.
addi r12 r13 16
load r7 r12
addi r12 r14 16
load r8 r12
add r7 r7 r8
jc r7 edge_color_back

; Front face and connector groups retain their original colors.
subi r0 r6 3
jc r0 edge_color_back_or_connector
imm r15 14
jmp edge_color_ready
edge_color_back_or_connector:
subi r0 r6 7
jc r0 edge_color_connector
imm r15 6
jmp edge_color_ready
edge_color_connector:
imm r15 3
jmp edge_color_ready

edge_color_back:
imm r15 11

edge_color_ready:
; Load x0,y0,x1,y1 into r7..r10.
muli r12 r13 2
load r7 r12
inc r12
load r8 r12

muli r12 r14 2
load r9 r12
inc r12
load r10 r12

; Convert the endpoint difference into fixed-point DDA increments.
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
; Convert the 10-bit fixed-point point to a display address.
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
subi r0 r6 11
jc r0 cube_ready
jmp select_edge

cube_ready:
imm r0 0
screen_swap r0

; Advance Y by 2 degrees.
muli r7 r2 99939083
muli r8 r3 3489950
add r0 r7 r8
divi0 100000000
mov r7 r0

muli r9 r3 99939083
muli r10 r2 3489950
sub r0 r9 r10
divi0 100000000
mov r9 r0

mov r2 r7
mov r3 r9

; Advance X by 1.3 degrees.
muli r7 r4 99974261
muli r8 r5 2268733
add r0 r7 r8
divi0 100000000
mov r7 r0

muli r9 r5 99974261
muli r10 r4 2268733
sub r0 r9 r10
divi0 100000000
mov r9 r0

mov r4 r7
mov r5 r9
jmp frame
