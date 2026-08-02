.screen 64 64
.memory 90

.reg sin_y r2
.reg cos_y r3
.reg sin_x r4
.reg cos_x r5
.reg item r6

; Edge-table and projection aliases.
.reg edge_value r7
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
; Geometry uses Q10 fixed point so successive rotations retain subpixel motion.

; Packed edge table. The integer coordinates make every listed edge
; length squared 144 or 152, and every vertex has degree three.

start:
  imm item 40
  imm edge_value 8
  store item edge_value
  inc item
  imm edge_value 12
  store item edge_value
  inc item
  imm edge_value 16
  store item edge_value
  inc item
  imm edge_value 29
  store item edge_value
  inc item
  imm edge_value 32
  store item edge_value
  inc item
  imm edge_value 37
  store item edge_value
  inc item
  imm edge_value 50
  store item edge_value
  inc item
  imm edge_value 53
  store item edge_value
  inc item
  imm edge_value 56
  store item edge_value
  inc item
  imm edge_value 71
  store item edge_value
  inc item
  imm edge_value 73
  store item edge_value
  inc item
  imm edge_value 77
  store item edge_value
  inc item
  imm edge_value 88
  store item edge_value
  inc item
  imm edge_value 94
  store item edge_value
  inc item
  imm edge_value 98
  store item edge_value
  inc item
  imm edge_value 109
  store item edge_value
  inc item
  imm edge_value 114
  store item edge_value
  inc item
  imm edge_value 119
  store item edge_value
  inc item
  imm edge_value 130
  store item edge_value
  inc item
  imm edge_value 135
  store item edge_value
  inc item
  imm edge_value 138
  store item edge_value
  inc item
  imm edge_value 151
  store item edge_value
  inc item
  imm edge_value 155
  store item edge_value
  inc item
  imm edge_value 159
  store item edge_value
  inc item
  imm edge_value 170
  store item edge_value
  inc item
  imm edge_value 191
  store item edge_value
  inc item
  imm edge_value 254
  store item edge_value
  inc item
  imm edge_value 275
  store item edge_value
  inc item
  imm edge_value 337
  store item edge_value
  inc item
  imm edge_value 379
  store item edge_value

  ; Start away from a symmetry axis so all three dimensions are visible.
  imm sin_y 42261826
  imm cos_y 90630779
  imm sin_x -34202014
  imm cos_x 93969262

frame:
  imm item 0

project_vertex:
  ; Select one of the four coordinate families.
  subi r0 item 7
  jc r0 non_cube_vertex

  ; Vertices 0..7: each index bit selects one sign.
  mov temp item
  divi r0 temp 4
  muli0 20480
  mov temp r0
  subi x temp 10240

  mov temp item
  divi temp temp 2
  mov addr temp
  divi r0 addr 2
  muli0 2
  mov addr r0
  sub r0 temp addr
  muli0 20480
  mov temp r0
  subi y temp 10240

  mov temp item
  mov addr temp
  divi r0 addr 2
  muli0 2
  mov addr r0
  sub r0 temp addr
  muli0 20480
  mov temp r0
  subi z temp 10240
  jmp vertex_ready

non_cube_vertex:
  subi r0 item 11
  jc r0 last_two_families

  ; Vertices 8..11: (0, +-6, +-16).
  subi addr item 8
  imm x 0

  mov temp addr
  divi r0 temp 2
  muli0 12288
  mov temp r0
  subi y temp 6144

  mov temp addr
  mov depth temp
  divi r0 depth 2
  muli0 2
  mov depth r0
  sub r0 temp depth
  muli0 32768
  mov temp r0
  subi z temp 16384
  jmp vertex_ready

last_two_families:
  subi r0 item 15
  jc r0 fourth_family

  ; Vertices 12..15: (+-6, +-16, 0).
  subi addr item 12
  mov temp addr
  divi r0 temp 2
  muli0 12288
  mov temp r0
  subi x temp 6144

  mov temp addr
  mov depth temp
  divi r0 depth 2
  muli0 2
  mov depth r0
  sub r0 temp depth
  muli0 32768
  mov temp r0
  subi y temp 16384
  imm z 0
  jmp vertex_ready

fourth_family:
  ; Vertices 16..19: (+-16, 0, +-6).
  subi addr item 16
  mov temp addr
  divi r0 temp 2
  muli0 32768
  mov temp r0
  subi x temp 16384
  imm y 0

  mov temp addr
  mov depth temp
  divi r0 depth 2
  muli0 2
  mov depth r0
  sub r0 temp depth
  muli0 12288
  mov temp r0
  subi z temp 6144

vertex_ready:
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
  addi addr item 70
  store addr depth

  ; Perspective projection with camera distance 110 and focal length 150.
  addi depth depth 112640
  muli r0 rx 150
  div0 depth
  addi0 32
  mov rx r0

  muli r0 ry 150
  div0 depth
  addi0 32
  mov ry r0

  muli addr item 2
  store addr rx
  inc addr
  store addr ry

  inc item
  subi r0 item 19
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

  imm item 0

select_edge:
  ; Decode packed endpoints a = edge/20 and b = edge-a*20.
  addi line_addr item 40
  load v0 line_addr
  mov v1 v0
  divi v1 v1 20
  muli line_addr v1 20
  sub v0 v0 line_addr

  ; An edge whose midpoint lies behind the origin uses dark gray.
  addi line_addr v1 70
  load line_x line_addr
  addi line_addr v0 70
  load line_y line_addr
  add line_x line_x line_y
  jc line_x edge_color_back

  ; Front edges retain the original four color groups.
  subi r0 item 7
  jc r0 edge_color_group_2
  imm color 14
  jmp edge_color_ready

edge_color_group_2:
  subi r0 item 15
  jc r0 edge_color_group_3
  imm color 3
  jmp edge_color_ready

edge_color_group_3:
  subi r0 item 23
  jc r0 edge_color_group_4
  imm color 4
  jmp edge_color_ready

edge_color_group_4:
  imm color 7
  jmp edge_color_ready

edge_color_back:
  imm color 11

edge_color_ready:
  ; Load x0,y0,x1,y1 into line_x..line_dy.
  muli line_addr v1 2
  load line_x line_addr
  inc line_addr
  load line_y line_addr

  muli line_addr v0 2
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
  subi r0 item 29
  jc r0 dodecahedron_ready
  jmp select_edge

dodecahedron_ready:
  imm r0 0
  screen_swap r0

  ; Advance Y by 1.4 degrees.
  muli next_sin sin_y 99970149
  muli mix0 cos_y 2443218
  add r0 next_sin mix0
  divi0 100000000
  mov next_sin r0

  muli next_cos cos_y 99970149
  muli mix1 sin_y 2443218
  sub r0 next_cos mix1
  divi0 100000000
  mov next_cos r0

  mov sin_y next_sin
  mov cos_y next_cos

  ; Advance X by 0.9 degrees.
  muli next_sin sin_x 99987663
  muli mix0 cos_x 1570732
  add r0 next_sin mix0
  divi0 100000000
  mov next_sin r0

  muli next_cos cos_x 99987663
  muli mix1 sin_x 1570732
  sub r0 next_cos mix1
  divi0 100000000
  mov next_cos r0

  mov sin_x next_sin
  mov cos_x next_cos
  jmp frame
