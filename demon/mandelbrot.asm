.screen 64 64

; Animated Mandelbrot zoom.
;
; Complex coordinates use Q24 fixed point (16777216 units per real unit).
;
; r2: frame
; r3: scale
; r4: c_re
; r5: c_im
; r6: z_re
; r7: z_im
; r8: z_re squared
; r9: z_im squared/temporary
; r10: temporary/color
; r11: iterations remaining
; r12: x*scale numerator
; r13: y*scale numerator
; r14: pixels left
; r15: rows left

start:
  imm r2 0
  imm r3 16777216

frame:
  ; Keep the scaled coordinates as running numerators. This preserves the
  ; exact floor(x*scale/64) coordinates without multiplying every pixel.
  muli r13 r3 -32
  imm r15 64

row:
  ; c_im = y*scale/64 + 0.186.
  mov r0 r13
  divi0 64
  addi0 3120562
  mov r5 r0

  muli r12 r3 -32
  imm r14 64

pixel:
  ; c_re = x*scale/64 - 0.745.
  mov r0 r12
  divi0 64
  addi0 -12499026
  mov r4 r0

  ; The radius-1/2 disk centered at -1/4 lies inside the main cardioid.
  ; Values remain in raw Q48 here, so the test introduces no approximation.
  mul r9 r5 r5
  addi r0 r4 4194304
  mov r8 r0
  mul0 r8
  add0 r9
  subi0 70368744177664
  jc r0 test_period_2_bulb
  jmp bounded

test_period_2_bulb:
  ; Reject the period-2 bulb analytically:
  ;   (c_re + 1)^2 + c_im^2 <= 1/16.
  ; Reuse c_im^2 from the cardioid-disk test.
  addi r0 r4 16777216
  mov r8 r0
  mul0 r8
  add0 r9
  subi0 17592186044416
  jc r0 outside_interior_disks
  jmp bounded

outside_interior_disks:
  ; The first iteration from z=0 always yields c. Every coordinate in this
  ; view is inside the escape radius, so begin at z=c with one iteration done.
  mov r6 r4
  mov r7 r5
  imm r11 63

iterate:
  mul r8 r6 r6
  mul r9 r7 r7

  ; Stop when |z| squared is at least 4.0.
  add r0 r8 r9
  subi0 1125899906842623
  jc r0 escaped

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
  dec r11
  jc r11 iterate

bounded:
  imm r10 0
  jmp emit

escaped:
  ; color = (iteration + frame/10) % 15 + 1.
  divi r8 r2 10
  addi0 64
  sub0 r11
  mov r10 r0
  divi r0 r10 15
  muli0 15
  mov r8 r0
  sub r10 r10 r8
  inc r10

emit:
  screen_data r10

  add r12 r12 r3
  dec r14
  jc r14 pixel

  add r13 r13 r3
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
