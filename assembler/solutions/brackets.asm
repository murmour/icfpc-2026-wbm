; Brackets checker for the processor in processor.txt.
;
; Register allocation:
;   r0, r1  ALU scratch
;   r4      remaining input characters
;   r6      original string length
;   r2      current character
;   r3      packed base-4 stack
;   r5      expected bracket type
;
; Stack representation:
;   opener types are nonzero two-bit digits: paren=1, square=2, curly=3.
;   The most recently opened bracket is the least significant digit.
;   Zero is therefore the empty stack.

start:
  read r4
  mov r6 r4
  imm r3 0

loop:
  jc r4 have_char
  mov r0 r3
  jc r0 unclosed
  andi0 9223372036854775807
  jc r0 unclosed
  write r3
halt:
  jmp halt

have_char:
  dec r4
  read r2

  ; floor(ASCII / 32) maps (), [], {} to type digits 1, 2, 3.
  mov r0 r2
  divi0 32
  mov r5 r0

  ; Bit 1 marks every opener except (, which is the sole even character.
  mov r0 r2
  andi0 2
  jc r0 push
  mov r0 r2
  andi0 1
  jc r0 close
  jmp push

close:
  mov r0 r3
  jc r0 can_close
  andi0 9223372036854775807
  jc r0 can_close

fail:
  mov r0 r6
  mov r1 r4
  alu sub
  write r0
  jmp halt

can_close:
  ; Compare the low two-bit digit before removing it.
  mov r0 r3
  andi0 3
  xor0 r5
  jc r0 fail

  ; Signed division needs a mask only when the packed stack is negative.
  mov r0 r3
  divi0 4
  jc r0 pop_store
  andi0 4611686018427387903
pop_store:
  mov r3 r0
  jmp loop

push:
  mov r0 r3
  muli0 4
  add0 r5
  mov r3 r0
  jmp loop

unclosed:
  inc r6
  write r6
  jmp halt
