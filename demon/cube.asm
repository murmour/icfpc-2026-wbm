.screen 64 64
.memory 24 48

.reg sin_y r2
.reg cos_y r3
.reg sin_x r4
.reg cos_x r5
.reg item r6

; Projection aliases.
.reg x r7
.reg y r8
.reg z r9
.reg rx r10
.reg rz r11
.reg ry r12
.reg depth r13
.reg addr r14
.reg temp r15

; Edge-rendering aliases for the same temporary registers.
.reg line_x r7
.reg line_y r8
.reg line_dx r9
.reg line_dy r10
.reg steps r11
.reg line_addr r12
.reg v0 r13
.reg v1 r14
.reg color r15

; Rotation-update aliases.
.reg next_sin r7
.reg mix0 r8
.reg next_cos r9
.reg mix1 r10

; Depth-shaded perspective cube rotating around the X and Y axes.
;
; Eight projected (x,y) vertex pairs occupy memory slots 0..15.
; Camera-space vertex depths occupy memory slots 16..23.
; Vertices on each z face use cyclic order, allowing all twelve edges
; to be selected arithmetically and drawn by one fixed-point DDA loop.
;
; Geometry uses Q12 fixed point so successive rotations retain subpixel motion.

start:
  imm sin_y 0
  imm cos_y 100000000
  imm sin_x -34202014
  imm cos_x 93969262

frame:
  ; Project all eight vertices.
  imm item 0

project_vertex:
  ; Reduce the vertex index to its cyclic face index and select z.
  mov addr item
  subi r0 addr 3
  jc r0 vertex_back
  imm z -61440
  jmp vertex_z_ready

vertex_back:
  subi addr addr 4
  imm z 61440

vertex_z_ready:
  ; y is negative for cyclic vertices 0,1 and positive for 2,3.
  subi r0 addr 1
  jc r0 vertex_y_positive
  imm y -61440
  jmp vertex_y_ready

vertex_y_positive:
  imm y 61440

vertex_y_ready:
  ; x follows the cyclic pattern negative, positive, positive, negative.
  mov r0 addr
  jc r0 vertex_x_middle
  imm x -61440
  jmp vertex_x_ready

vertex_x_middle:
  imm r0 3
  sub0 addr
  jc r0 vertex_x_positive
  imm x -61440
  jmp vertex_x_ready

vertex_x_positive:
  imm x 61440

vertex_x_ready:
  ; Rotate around Y:
  ;   x1 = x*cos_y + z*sin_y
  ;   z1 = z*cos_y - x*sin_y
  mul rx x cos_y
  mul temp z sin_y
  add r0 rx temp
  divi0 100000000
  mov rx r0

  mul rz z cos_y
  mul temp x sin_y
  sub r0 rz temp
  divi0 100000000
  mov rz r0

  ; Rotate around X:
  ;   y2 = y*cos_x - z1*sin_x
  ;   z2 = y*sin_x + z1*cos_x
  mul ry y cos_x
  mul temp rz sin_x
  sub r0 ry temp
  divi0 100000000
  mov ry r0

  mul depth y sin_x
  mul temp rz cos_x
  add r0 depth temp
  divi0 100000000
  mov depth r0

  ; Preserve camera-space depth for dynamic edge shading.
  addi addr item 16
  store addr depth

  ; Perspective projection with camera distance 90.
  addi depth depth 368640
  muli r0 rx 90
  div0 depth
  addi0 32
  mov rx r0

  muli r0 ry 90
  div0 depth
  addi0 32
  mov ry r0

  ; Store projected x and y.
  muli addr item 2
  store addr rx
  inc addr
  store addr ry

  inc item
  subi r0 item 7
  jc r0 projection_done
  jmp project_vertex

projection_done:
  ; Clear the complete back buffer.
  imm line_x 0
  screen_addr line_x
  imm line_y 4096

clear_pixel:
  screen_data line_x
  dec line_y
  jc line_y clear_pixel

  ; Edges 0..3 surround the first face, 4..7 surround the second,
  ; and 8..11 connect corresponding face vertices.
  imm item 0

select_edge:
  subi r0 item 7
  jc r0 connector_edge
  subi r0 item 3
  jc r0 back_face_edge

  ; First face: e -> e+1, with edge 3 wrapping to vertex 0.
  mov v0 item
  addi v1 item 1
  subi r0 item 2
  jc r0 front_face_wrap
  jmp load_edge

front_face_wrap:
  imm v1 0
  jmp load_edge

; Second face: e -> e+1, with edge 7 wrapping to vertex 4.
back_face_edge:
  mov v0 item
  addi v1 item 1
  subi r0 item 6
  jc r0 back_face_wrap
  jmp load_edge

back_face_wrap:
  imm v1 4
  jmp load_edge

; Connector e uses vertices e-8 and e-4.
connector_edge:
  subi v0 item 8
  addi v1 v0 4

load_edge:
  ; An edge whose midpoint lies behind the origin uses dark gray.
  addi line_addr v0 16
  load line_x line_addr
  addi line_addr v1 16
  load line_y line_addr
  add line_x line_x line_y
  jc line_x edge_color_back

  ; Front face and connector groups retain their original colors.
  subi r0 item 3
  jc r0 edge_color_back_or_connector
  imm color 14
  jmp edge_color_ready

edge_color_back_or_connector:
  subi r0 item 7
  jc r0 edge_color_connector
  imm color 6
  jmp edge_color_ready

edge_color_connector:
  imm color 3
  jmp edge_color_ready

edge_color_back:
  imm color 11

edge_color_ready:
  ; Load x0,y0,x1,y1 into line_x..line_dy.
  muli line_addr v0 2
  load line_x line_addr
  inc line_addr
  load line_y line_addr

  muli line_addr v1 2
  load line_dx line_addr
  inc line_addr
  load line_dy line_addr

  ; Convert the endpoint difference into fixed-point DDA increments.
  sub line_dx line_dx line_x
  sub line_dy line_dy line_y

  mov steps line_dx
  jc steps edge_abs_dx_ready
  neg steps

edge_abs_dx_ready:
  mov line_addr line_dy
  jc line_addr edge_abs_dy_ready
  neg line_addr

edge_abs_dy_ready:
  sub r0 steps line_addr
  jc r0 edge_steps_ready
  mov steps line_addr

edge_steps_ready:
  jc steps edge_steps_nonzero
  imm steps 1

edge_steps_nonzero:
  muli line_x line_x 1024
  muli line_y line_y 1024
  muli r0 line_dx 1024
  div0 steps
  mov line_dx r0
  muli r0 line_dy 1024
  div0 steps
  mov line_dy r0
  inc steps

draw_edge_pixel:
  ; Convert the 10-bit fixed-point point to a display address.
  divi r0 line_y 1024
  muli0 64
  mov line_addr r0
  divi v0 line_x 1024
  add line_addr line_addr v0
  screen_addr line_addr
  screen_data color

  add line_x line_x line_dx
  add line_y line_y line_dy
  dec steps
  jc steps draw_edge_pixel

  inc item
  subi r0 item 11
  jc r0 cube_ready
  jmp select_edge

cube_ready:
  imm r0 0
  screen_swap r0

  ; Advance Y by 2 degrees.
  muli next_sin sin_y 99939083
  muli mix0 cos_y 3489950
  add r0 next_sin mix0
  divi0 100000000
  mov next_sin r0

  muli next_cos cos_y 99939083
  muli mix1 sin_y 3489950
  sub r0 next_cos mix1
  divi0 100000000
  mov next_cos r0

  mov sin_y next_sin
  mov cos_y next_cos

  ; Advance X by 1.3 degrees.
  muli next_sin sin_x 99974261
  muli mix0 cos_x 2268733
  add r0 next_sin mix0
  divi0 100000000
  mov next_sin r0

  muli next_cos cos_x 99974261
  muli mix1 sin_x 2268733
  sub r0 next_cos mix1
  divi0 100000000
  mov next_cos r0

  mov sin_x next_sin
  mov cos_x next_cos
  jmp frame
