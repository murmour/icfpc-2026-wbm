.screen 32 24
.kind plotter

.reg x0 r2
.reg addr r2
.reg y0 r3
.reg error r3
.reg left r4
.reg dx r5
.reg x_step r6
.reg dy r7
.reg y_step r8

; Draw one Bresenham line per round on the 32x24 display.
; The processor blocks on the next read after the final round.
;
; During setup:
;   x0 and y0 are retained; x1 and y1 pass directly through r0
; During drawing:
;   addr is the display address, error the branch error, and left the
;   scaled number of pixels remaining
; Shared:
;   dx is abs(x1-x0), x_step the x address step
;   dy is signed, and y_step is the y address step
; r1 remains 15 while drawing and supplies both the color and counter step.

next_round:
  read x0
  read y0
  read r0
  sub0 x0
  mov dx r0
  jc r0 dx_positive
  imm x_step -1
  neg dx
  jmp dx_done

dx_positive:
  imm x_step 1

dx_done:
  read r0
  sub0 y0
  mov dy r0
  jc r0 dy_positive
  imm y_step -32
  jmp dy_done

dy_positive:
  imm y_step 32
  neg dy

dy_done:
  mov r0 y0
  muli0 32
  add0 x0
  mov addr r0

  ; abs(dy) > dx selects the steep loop.
  imm r0 0
  sub0 dy
  sub0 dx
  jc r0 steep_init

  ; The shallow branch error is 2*err-dx = dx+2*dy.
  mov r0 dx
  add0 dy
  add0 dy
  mov error r0
  mov r0 dx
  addi0 1
  muli0 15
  mov left r0

shallow_loop:
  screen_addr addr
  screen_data r1
  jc error shallow_skip_y
  mov r0 error
  add0 dx
  add0 dx
  mov error r0
  mov r0 addr
  add0 y_step
  mov addr r0

shallow_skip_y:
  mov r0 error
  add0 dy
  add0 dy
  mov error r0
  mov r0 addr
  add0 x_step
  mov addr r0
  mov r0 left
  sub0 r1
  mov left r0
  jc r0 shallow_loop
  jmp finish_round

steep_init:
  ; The steep branch error is dy-2*err = -2*dx-dy.
  imm r0 0
  sub0 dx
  sub0 dx
  sub0 dy
  mov error r0
  imm r0 1
  sub0 dy
  muli0 15
  mov left r0

steep_loop:
  screen_addr addr
  screen_data r1
  jc error steep_skip_x
  mov r0 error
  sub0 dy
  sub0 dy
  mov error r0
  mov r0 addr
  add0 x_step
  mov addr r0

steep_skip_x:
  mov r0 error
  sub0 dx
  sub0 dx
  mov error r0
  mov r0 addr
  add0 y_step
  mov addr r0
  mov r0 left
  sub0 r1
  mov left r0
  jc r0 steep_loop

finish_round:
  screen_swap r0
  jmp next_round
