.reg ch r2
.reg stack r3
.reg left r4
.reg expected r5
.reg length r6

; Brackets checker for the processor in processor.txt.
;
; Stack representation:
;   opener types are nonzero two-bit digits: paren=1, square=2, curly=3.
;   The most recently opened bracket is the least significant digit.
;   Zero is therefore the empty stack.

start:
  read left
  mov length left
  imm stack 0

loop:
  jc left have_char
  mov r0 stack
  jc r0 unclosed
  andi0 9223372036854775807
  jc r0 unclosed
  write stack

halt:
  jmp halt

have_char:
  dec left
  read ch

  ; floor(ASCII / 32) maps (), [], {} to type digits 1, 2, 3.
  mov r0 ch
  divi0 32
  mov expected r0

  ; Bit 1 marks every opener except (, which is the sole even character.
  mov r0 ch
  andi0 2
  jc r0 push
  mov r0 ch
  andi0 1
  jc r0 close
  jmp push

close:
  mov r0 stack
  jc r0 can_close
  andi0 9223372036854775807
  jc r0 can_close

fail:
  mov r0 length
  mov r1 left
  sub0 r1
  write r0
  jmp halt

can_close:
  ; Compare the low two-bit digit before removing it.
  mov r0 stack
  andi0 3
  xor0 expected
  jc r0 fail

  ; Signed division needs a mask only when the packed stack is negative.
  mov r0 stack
  divi0 4
  jc r0 pop_store
  andi0 4611686018427387903

pop_store:
  mov stack r0
  jmp loop

push:
  mov r0 stack
  muli0 4
  add0 expected
  mov stack r0
  jmp loop

unclosed:
  inc length
  write length
  jmp halt
