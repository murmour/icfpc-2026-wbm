.screen 64 64
.memory 40

.reg vx r2
.reg vy r3
.reg vz r4
.reg vw r5
.reg item r6
.reg t0 r7
.reg t1 r8
.reg t2 r9
.reg px r10
.reg py r11
.reg addr r12
.reg sine r13
.reg cosine r14
.reg color r15

; Edge-rendering aliases for the projection temporaries.
.reg line_x r7
.reg line_y r8
.reg line_dx r9
.reg line_dy r10
.reg steps r11
.reg line_work r12
.reg v0 r13
.reg v1 r14

; Oscillator-update aliases.
.reg old_sin r7
.reg old_cos r8
.reg next_sin r9
.reg next_cos r10
.reg mix r11

; Rotating four-dimensional hypercube (tesseract).
;
; Memory:
;   0..31   sixteen projected (x,y) pairs
;   32..39  (sin,cos) oscillator pairs for XW, YZ, ZW, and XY
;
; Vertex coordinates use a scale of 3584 to preserve fractional motion
; through all four rotations. All four rotations begin at zero.

start:
  imm addr 32
  imm sine 0
  imm cosine 1000000000
  store addr sine
  inc addr
  store addr cosine
  inc addr
  store addr sine
  inc addr
  store addr cosine
  inc addr
  store addr sine
  inc addr
  store addr cosine
  inc addr
  store addr sine
  inc addr
  store addr cosine

frame:
  ; Project all sixteen vertices.
  imm item 0

project_vertex:
  ; Decode the four coordinate signs from the vertex index.
  mov r0 item
  andi0 1
  jc r0 vertex_x_positive
  imm vx -3584
  jmp vertex_x_ready

vertex_x_positive:
  imm vx 3584

vertex_x_ready:

  mov r0 item
  andi0 2
  jc r0 vertex_y_positive
  imm vy -3584
  jmp vertex_y_ready

vertex_y_positive:
  imm vy 3584

vertex_y_ready:

  mov r0 item
  andi0 4
  jc r0 vertex_z_positive
  imm vz -3584
  jmp vertex_z_ready

vertex_z_positive:
  imm vz 3584

vertex_z_ready:

  mov r0 item
  andi0 8
  jc r0 vertex_w_positive
  imm vw -3584
  jmp vertex_w_ready

vertex_w_positive:
  imm vw 3584

vertex_w_ready:
  ; Rotate XW.
  imm addr 32
  load sine addr
  inc addr
  load cosine addr
  mul t0 vx cosine
  mul t1 vw sine
  sub r0 t0 t1
  divi0 1000000000
  mov t0 r0
  mul t1 vx sine
  mul t2 vw cosine
  add r0 t1 t2
  divi0 1000000000
  mov t1 r0
  mov vx t0
  mov vw t1

  ; Rotate YZ.
  imm addr 34
  load sine addr
  inc addr
  load cosine addr
  mul t0 vy cosine
  mul t1 vz sine
  sub r0 t0 t1
  divi0 1000000000
  mov t0 r0
  mul t1 vy sine
  mul t2 vz cosine
  add r0 t1 t2
  divi0 1000000000
  mov t1 r0
  mov vy t0
  mov vz t1

  ; Rotate ZW.
  imm addr 36
  load sine addr
  inc addr
  load cosine addr
  mul t0 vz cosine
  mul t1 vw sine
  sub r0 t0 t1
  divi0 1000000000
  mov t0 r0
  mul t1 vz sine
  mul t2 vw cosine
  add r0 t1 t2
  divi0 1000000000
  mov t1 r0
  mov vz t0
  mov vw t1

  ; Rotate XY.
  imm addr 38
  load sine addr
  inc addr
  load cosine addr
  mul t0 vx cosine
  mul t1 vy sine
  sub r0 t0 t1
  divi0 1000000000
  mov t0 r0
  mul t1 vx sine
  mul t2 vy cosine
  add r0 t1 t2
  divi0 1000000000
  mov t1 r0
  mov vx t0
  mov vy t1

  ; 4D perspective. t0-t2 retain x,y,z at a scale of 10240.
  imm sine 11469
  sub sine sine vw
  muli r0 vx 21504
  div0 sine
  mov t0 r0
  muli r0 vy 21504
  div0 sine
  mov t1 r0
  muli r0 vz 21504
  div0 sine
  mov t2 r0

  ; 3D perspective.
  imm sine 46080
  sub sine sine t2
  muli r0 t0 55
  div0 sine
  addi0 32
  mov px r0
  muli r0 t1 55
  div0 sine
  addi0 32
  mov py r0

  ; Clamp projected endpoints because the physical screen-address port does
  ; not clip lines for us.
  jc px project_x_nonnegative
  imm px 0
  jmp project_x_ready

project_x_nonnegative:
  subi r0 px 63
  jc r0 project_x_high
  jmp project_x_ready

project_x_high:
  imm px 63

project_x_ready:

  jc py project_y_nonnegative
  imm py 0
  jmp project_y_ready

project_y_nonnegative:
  subi r0 py 63
  jc r0 project_y_high
  jmp project_y_ready

project_y_high:
  imm py 63

project_y_ready:
  ; Store projected x,y.
  muli addr item 2
  store addr px
  inc addr
  store addr py

  inc item
  subi r0 item 15
  jc r0 projection_done
  jmp project_vertex

projection_done:
  ; Clear the back buffer.
  imm line_x 0
  screen_addr line_x
  imm line_y 4096

clear_pixel:
  screen_data line_x
  dec line_y
  jc line_y clear_pixel
  ; Each group of eight edges belongs to one coordinate dimension.
  imm item 0

select_edge:
  divi line_work item 8
  muli v0 line_work 8
  sub v0 item v0

  ; Insert a zero bit into the three-bit edge slot to obtain endpoint A.
  jc line_work edge_dimension_nonzero
  muli v0 v0 2
  addi v1 v0 1
  jmp edge_ready

edge_dimension_nonzero:
  subi r0 line_work 1
  jc r0 edge_dimension_2_or_3

  ; Dimension 1.
  mov r0 v0
  andi0 1
  mov v1 r0
  divi r0 v0 2
  muli0 4
  add0 v1
  mov v0 r0
  addi v1 v0 2
  jmp edge_ready

edge_dimension_2_or_3:
  subi r0 line_work 2
  jc r0 edge_dimension_3

  ; Dimension 2.
  mov r0 v0
  andi0 3
  mov v1 r0
  divi r0 v0 4
  muli0 8
  add0 v1
  mov v0 r0
  addi v1 v0 4
  jmp edge_ready

edge_dimension_3:
  addi v1 v0 8

edge_ready:
  ; Give each edge slot one stable color from the vivid half of the palette.
  mov r0 item
  andi0 7
  addi0 1
  mov color r0

  ; Load x0,y0,x1,y1 into line_x..line_dy.
  muli steps v0 2
  load line_x steps
  inc steps
  load line_y steps
  muli steps v1 2
  load line_dx steps
  inc steps
  load line_dy steps

  ; Fixed-point DDA.
  sub line_dx line_dx line_x
  sub line_dy line_dy line_y
  mov steps line_dx
  jc steps edge_abs_dx_ready
  neg steps

edge_abs_dx_ready:
  mov line_work line_dy
  jc line_work edge_abs_dy_ready
  neg line_work

edge_abs_dy_ready:
  sub r0 steps line_work
  jc r0 edge_steps_ready
  mov steps line_work

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
  mov line_work r0
  divi v0 line_x 1024
  add line_work line_work v0
  screen_addr line_work
  screen_data color
  add line_x line_x line_dx
  add line_y line_y line_dy
  dec steps
  jc steps draw_edge_pixel

  inc item
  subi r0 item 31
  jc r0 hypercube_ready
  jmp select_edge

hypercube_ready:
  imm r0 0
  screen_swap r0

  ; Advance XW by 0.017 radians.
  imm addr 32
  load old_sin addr
  inc addr
  load old_cos addr
  muli next_sin old_sin 999855503
  muli next_cos old_cos 16999181
  add r0 next_sin next_cos
  divi0 1000000000
  mov next_sin r0
  muli next_cos old_cos 999855503
  muli mix old_sin 16999181
  sub r0 next_cos mix
  divi0 1000000000
  mov next_cos r0
  imm addr 32
  store addr next_sin
  inc addr
  store addr next_cos

  ; Advance YZ by 0.013 radians.
  imm addr 34
  load old_sin addr
  inc addr
  load old_cos addr
  muli next_sin old_sin 999915501
  muli next_cos old_cos 12999634
  add r0 next_sin next_cos
  divi0 1000000000
  mov next_sin r0
  muli next_cos old_cos 999915501
  muli mix old_sin 12999634
  sub r0 next_cos mix
  divi0 1000000000
  mov next_cos r0
  imm addr 34
  store addr next_sin
  inc addr
  store addr next_cos

  ; Advance ZW by 0.009 radians.
  imm addr 36
  load old_sin addr
  inc addr
  load old_cos addr
  muli next_sin old_sin 999959500
  muli next_cos old_cos 8999879
  add r0 next_sin next_cos
  divi0 1000000000
  mov next_sin r0
  muli next_cos old_cos 999959500
  muli mix old_sin 8999879
  sub r0 next_cos mix
  divi0 1000000000
  mov next_cos r0
  imm addr 36
  store addr next_sin
  inc addr
  store addr next_cos

  ; Advance XY by 0.006 radians.
  imm addr 38
  load old_sin addr
  inc addr
  load old_cos addr
  muli next_sin old_sin 999982000
  muli next_cos old_cos 5999964
  add r0 next_sin next_cos
  divi0 1000000000
  mov next_sin r0
  muli next_cos old_cos 999982000
  muli mix old_sin 5999964
  sub r0 next_cos mix
  divi0 1000000000
  mov next_cos r0
  imm addr 38
  store addr next_sin
  inc addr
  store addr next_cos

  jmp frame
