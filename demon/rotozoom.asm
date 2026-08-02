.screen 64 64
.memory 17

.reg phase r2
.reg du r3
.reg dv r4
; The table aliases are used only during initialization.
.reg table_addr r4
.reg row_u r5
.reg table_value r5
.reg row_v r6
.reg u r7
.reg v r8
.reg pixels r9
.reg rows r10
.reg sine r11
.reg cosine r12
.reg zoom r13
.reg temp r14
.reg color r15

; Fixed-point rotozoomed checkerboard using 16 registers.
;
; Initialize the 17-entry quarter-wave sine table.

start:
  imm phase 0
  imm table_addr 0
  imm table_value 0
  store table_addr table_value
  imm table_addr 1
  imm table_value 100
  store table_addr table_value
  imm table_addr 2
  imm table_value 200
  store table_addr table_value
  imm table_addr 3
  imm table_value 297
  store table_addr table_value
  imm table_addr 4
  imm table_value 392
  store table_addr table_value
  imm table_addr 5
  imm table_value 483
  store table_addr table_value
  imm table_addr 6
  imm table_value 569
  store table_addr table_value
  imm table_addr 7
  imm table_value 650
  store table_addr table_value
  imm table_addr 8
  imm table_value 724
  store table_addr table_value
  imm table_addr 9
  imm table_value 792
  store table_addr table_value
  imm table_addr 10
  imm table_value 851
  store table_addr table_value
  imm table_addr 11
  imm table_value 903
  store table_addr table_value
  imm table_addr 12
  imm table_value 946
  store table_addr table_value
  imm table_addr 13
  imm table_value 980
  store table_addr table_value
  imm table_addr 14
  imm table_value 1004
  store table_addr table_value
  imm table_addr 15
  imm table_value 1019
  store table_addr table_value
  imm table_addr 16
  imm table_value 1024
  store table_addr table_value

frame:
  ; sine = sin(phase). du is the quadrant, dv the table offset, and
  ; row_u a temporary.
  divi du phase 16
  muli row_u du 16
  sub dv phase row_u
  jeq du 1 sin_mirror
  jeq du 3 sin_mirror
  jmp sin_lookup

sin_mirror:
  imm r0 16
  mov r1 dv
  sub0 r1
  mov dv r0

sin_lookup:
  load sine dv
  subi r0 du 1
  jc r0 sin_negate
  jmp sin_done

sin_negate:
  neg sine

sin_done:
  ; cosine = cos(phase) = sin(phase + 16).
  addi row_v phase 16
  subi r0 row_v 63
  jc r0 wrap_cos
  jmp cos_phase_ready

wrap_cos:
  subi row_v row_v 64

cos_phase_ready:
  divi du row_v 16
  muli row_u du 16
  sub dv row_v row_u
  jeq du 1 cos_mirror
  jeq du 3 cos_mirror
  jmp cos_lookup

cos_mirror:
  imm r0 16
  mov r1 dv
  sub0 r1
  mov dv r0

cos_lookup:
  load cosine dv
  subi r0 du 1
  jc r0 cos_negate
  jmp cos_done

cos_negate:
  neg cosine

cos_done:
  ; Apply a small sinusoidal zoom and build the affine increments.
  divi r0 sine 4
  addi0 1024
  mov zoom r0
  mul temp cosine zoom
  divi du temp 1024
  mul temp sine zoom
  divi dv temp 1024

  ; Start at the transformed upper-left corner.
  sub temp du dv
  muli row_u temp 32
  neg row_u
  add temp dv du
  muli row_v temp 32
  neg row_v
  imm rows 64

row:
  mov u row_u
  mov v row_v
  imm pixels 64

pixel:
  ; Reduce u and v modulo 16384 without a dedicated remainder operation.
  divi sine u 16384
  muli cosine sine 16384
  sub zoom u cosine
  divi sine v 16384
  muli cosine sine 16384
  sub temp v cosine

  ; XOR the high half-period bits to form the checkerboard.
  subi r0 zoom 8191
  jc r0 u_high
  subi r0 temp 8191
  jc r0 light
  jmp dark

u_high:
  subi r0 temp 8191
  jc r0 dark
  jmp light

light:
  imm color 14
  jmp emit

dark:
  imm color 2

emit:
  screen_data color

  add u u du
  add v v dv
  dec pixels
  jc pixels pixel

  sub row_u row_u dv
  add row_v row_v du
  dec rows
  jc rows row

  imm color 0
  screen_swap color
  inc phase
  subi r0 phase 63
  jc r0 wrap_phase
  jmp frame

wrap_phase:
  subi phase phase 64
  jmp frame
