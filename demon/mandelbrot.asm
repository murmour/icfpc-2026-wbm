.screen 64 64

.reg frame r2
.reg scale r3
.reg cr r4
.reg ci r5
.reg zr r6
.reg zi r7
.reg zr2 r8
.reg zi2 r9
.reg temp r10
.reg iters r11
.reg x_num r12
.reg y_num r13
.reg pixels r14
.reg rows r15

; Animated Mandelbrot zoom.
;
; Complex coordinates use Q24 fixed point (16777216 units per real unit).

start:
  imm frame 0
  imm scale 16777216

frame:
  ; Keep the scaled coordinates as running numerators. This preserves the
  ; exact floor(x*scale/64) coordinates without multiplying every pixel.
  muli y_num scale -32
  imm rows 64

row:
  ; c_im = y*scale/64 + 0.186.
  mov r0 y_num
  divi0 64
  addi0 3120562
  mov ci r0

  muli x_num scale -32
  imm pixels 64

pixel:
  ; c_re = x*scale/64 - 0.745.
  mov r0 x_num
  divi0 64
  addi0 -12499026
  mov cr r0

  ; The radius-1/2 disk centered at -1/4 lies inside the main cardioid.
  ; Values remain in raw Q48 here, so the test introduces no approximation.
  mul zi2 ci ci
  addi r0 cr 4194304
  mov zr2 r0
  mul0 zr2
  add0 zi2
  subi0 70368744177664
  jc r0 test_period_2_bulb
  jmp bounded

test_period_2_bulb:
  ; Reject the period-2 bulb analytically:
  ;   (c_re + 1)^2 + c_im^2 <= 1/16.
  ; Reuse c_im^2 from the cardioid-disk test.
  addi r0 cr 16777216
  mov zr2 r0
  mul0 zr2
  add0 zi2
  subi0 17592186044416
  jc r0 outside_interior_disks
  jmp bounded

outside_interior_disks:
  ; The first iteration from z=0 always yields c. Every coordinate in this
  ; view is inside the escape radius, so begin at z=c with one iteration done.
  mov zr cr
  mov zi ci
  imm iters 63

iterate:
  mul zr2 zr zr
  mul zi2 zi zi

  ; Stop when |z| squared is at least 4.0.
  add r0 zr2 zi2
  subi0 1125899906842623
  jc r0 escaped

  ; z_re = z_re^2 - z_im^2 + c_re.
  sub r0 zr2 zi2
  divi0 16777216
  add0 cr
  mov zr2 r0

  ; z_im = 2*z_re*z_im + c_im, using the old components.
  mul r0 zr zi
  muli0 2
  divi0 16777216
  add0 ci
  mov zi2 r0

  mov zr zr2
  mov zi zi2
  dec iters
  jc iters iterate

bounded:
  imm temp 0
  jmp emit

escaped:
  ; color = (iteration + frame/10) % 15 + 1.
  divi zr2 frame 10
  addi0 64
  sub0 iters
  mov temp r0
  divi r0 temp 15
  muli0 15
  mov zr2 r0
  sub temp temp zr2
  inc temp

emit:
  screen_data temp

  add x_num x_num scale
  dec pixels
  jc pixels pixel

  add y_num y_num scale
  dec rows
  jc rows row

  imm temp 0
  screen_swap temp

  ; scale *= 0.98.
  muli r0 scale 98
  divi0 100
  mov scale r0
  inc frame
  jmp frame
