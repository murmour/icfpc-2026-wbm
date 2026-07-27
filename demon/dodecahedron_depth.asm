.screen 64 64
.memory 90

; Depth-shaded perspective dodecahedron rotating around two axes.
;
; Vertices use an integer golden-ratio approximation:
;   (+-10, +-10, +-10)
;   (0, +-6, +-16)
;   (+-6, +-16, 0)
;   (+-16, 0, +-6)
;
; Memory 0..39 stores twenty projected (x,y) pairs. Memory 40..69
; stores thirty edges packed as vertex_a * 20 + vertex_b. Memory
; 70..89 stores the camera-space depth of each projected vertex.
;
; r2,r3   sin/cos of Y rotation, scale 1,000,000
; r4,r5   sin/cos of X rotation, scale 1,000,000
; r6      vertex / edge index
; r7-r15  geometry and line-rendering temporaries

; Packed edge table. The integer coordinates make every listed edge
; length squared 144 or 152, and every vertex has degree three.
imm r6 40
imm r7 8
store r6 r7
inc r6
imm r7 12
store r6 r7
inc r6
imm r7 16
store r6 r7
inc r6
imm r7 29
store r6 r7
inc r6
imm r7 32
store r6 r7
inc r6
imm r7 37
store r6 r7
inc r6
imm r7 50
store r6 r7
inc r6
imm r7 53
store r6 r7
inc r6
imm r7 56
store r6 r7
inc r6
imm r7 71
store r6 r7
inc r6
imm r7 73
store r6 r7
inc r6
imm r7 77
store r6 r7
inc r6
imm r7 88
store r6 r7
inc r6
imm r7 94
store r6 r7
inc r6
imm r7 98
store r6 r7
inc r6
imm r7 109
store r6 r7
inc r6
imm r7 114
store r6 r7
inc r6
imm r7 119
store r6 r7
inc r6
imm r7 130
store r6 r7
inc r6
imm r7 135
store r6 r7
inc r6
imm r7 138
store r6 r7
inc r6
imm r7 151
store r6 r7
inc r6
imm r7 155
store r6 r7
inc r6
imm r7 159
store r6 r7
inc r6
imm r7 170
store r6 r7
inc r6
imm r7 191
store r6 r7
inc r6
imm r7 254
store r6 r7
inc r6
imm r7 275
store r6 r7
inc r6
imm r7 337
store r6 r7
inc r6
imm r7 379
store r6 r7

; Start away from a symmetry axis so all three dimensions are visible.
imm r2 422618
imm r3 906308
imm r4 -342020
imm r5 939693

frame:
imm r6 0

project_vertex:
; Select one of the four coordinate families.
subi r0 r6 7
jc r0 non_cube_vertex

; Vertices 0..7: each index bit selects one sign.
mov r15 r6
divi r15 r15 4
muli r15 r15 20
subi r7 r15 10

mov r15 r6
divi r15 r15 2
mov r14 r15
divi r14 r14 2
muli r14 r14 2
sub r15 r15 r14
muli r15 r15 20
subi r8 r15 10

mov r15 r6
mov r14 r15
divi r14 r14 2
muli r14 r14 2
sub r15 r15 r14
muli r15 r15 20
subi r9 r15 10
jmp vertex_ready

non_cube_vertex:
subi r0 r6 11
jc r0 last_two_families

; Vertices 8..11: (0, +-6, +-16).
subi r14 r6 8
imm r7 0

mov r15 r14
divi r15 r15 2
muli r15 r15 12
subi r8 r15 6

mov r15 r14
mov r13 r15
divi r13 r13 2
muli r13 r13 2
sub r15 r15 r13
muli r15 r15 32
subi r9 r15 16
jmp vertex_ready

last_two_families:
subi r0 r6 15
jc r0 fourth_family

; Vertices 12..15: (+-6, +-16, 0).
subi r14 r6 12
mov r15 r14
divi r15 r15 2
muli r15 r15 12
subi r7 r15 6

mov r15 r14
mov r13 r15
divi r13 r13 2
muli r13 r13 2
sub r15 r15 r13
muli r15 r15 32
subi r8 r15 16
imm r9 0
jmp vertex_ready

fourth_family:
; Vertices 16..19: (+-16, 0, +-6).
subi r14 r6 16
mov r15 r14
divi r15 r15 2
muli r15 r15 32
subi r7 r15 16
imm r8 0

mov r15 r14
mov r13 r15
divi r13 r13 2
muli r13 r13 2
sub r15 r15 r13
muli r15 r15 12
subi r9 r15 6

vertex_ready:
; Rotate around Y:
;   x1 = x*cos_y + z*sin_y
;   z1 = z*cos_y - x*sin_y
mul r10 r7 r3
mul r15 r9 r2
add r10 r10 r15
divi r10 r10 1000000

mul r11 r9 r3
mul r15 r7 r2
sub r11 r11 r15
divi r11 r11 1000000

; Rotate around X:
;   y2 = y*cos_x - z1*sin_x
;   z2 = y*sin_x + z1*cos_x
mul r12 r8 r5
mul r15 r11 r4
sub r12 r12 r15
divi r12 r12 1000000

mul r13 r8 r4
mul r15 r11 r5
add r13 r13 r15
divi r13 r13 1000000

; Preserve camera-space depth for dynamic edge shading.
addi r14 r6 70
store r14 r13

; Perspective projection with camera distance 110 and focal length 150.
addi r13 r13 110
muli r10 r10 150
div r10 r10 r13
addi r10 r10 32

muli r12 r12 150
div r12 r12 r13
addi r12 r12 32

muli r14 r6 2
store r14 r10
inc r14
store r14 r12

inc r6
subi r0 r6 19
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

imm r6 0

select_edge:
; Decode packed endpoints a = edge/20 and b = edge-a*20.
addi r12 r6 40
load r13 r12
mov r14 r13
divi r14 r14 20
muli r12 r14 20
sub r13 r13 r12

; An edge whose midpoint lies behind the origin uses dark gray.
addi r12 r14 70
load r7 r12
addi r12 r13 70
load r8 r12
add r7 r7 r8
jc r7 edge_color_back

; Front edges retain the original four color groups.
subi r0 r6 7
jc r0 edge_color_group_2
imm r15 14
jmp edge_color_ready
edge_color_group_2:
subi r0 r6 15
jc r0 edge_color_group_3
imm r15 3
jmp edge_color_ready
edge_color_group_3:
subi r0 r6 23
jc r0 edge_color_group_4
imm r15 4
jmp edge_color_ready
edge_color_group_4:
imm r15 7
jmp edge_color_ready

edge_color_back:
imm r15 11

edge_color_ready:
; Load x0,y0,x1,y1 into r7..r10.
muli r12 r14 2
load r7 r12
inc r12
load r8 r12

muli r12 r13 2
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
muli r9 r9 1024
div r9 r9 r11
muli r10 r10 1024
div r10 r10 r11
inc r11

draw_edge_pixel:
divi r12 r8 1024
muli r12 r12 64
divi r13 r7 1024
add r12 r12 r13
screen_addr r12
screen_data r15

add r7 r7 r9
add r8 r8 r10
dec r11
jc r11 draw_edge_pixel

inc r6
subi r0 r6 29
jc r0 dodecahedron_ready
jmp select_edge

dodecahedron_ready:
imm r0 0
screen_swap r0

; Advance Y by 1.4 degrees.
muli r7 r2 999702
muli r8 r3 24432
add r7 r7 r8
divi r7 r7 1000000

muli r9 r3 999702
muli r10 r2 24432
sub r9 r9 r10
divi r9 r9 1000000

mov r2 r7
mov r3 r9

; Advance X by 0.9 degrees.
muli r7 r4 999877
muli r8 r5 15707
add r7 r7 r8
divi r7 r7 1000000

muli r9 r5 999877
muli r10 r4 15707
sub r9 r9 r10
divi r9 r9 1000000

mov r4 r7
mov r5 r9
jmp frame
