package main

type Program struct {
	Name   string
	Pipes  []*Pipe
	Blocks []*Block
}

type Pipe struct {
	Name    string
	MinSize int
	MaxSize int
	Line    int
}

type Block struct {
	Name string
	Body []Stmt
	Line int
}

type Stmt interface {
	stmt()
}

type InstructionKind string

const (
	InstructionLoad       InstructionKind = "load"
	InstructionCopy       InstructionKind = "copy"
	InstructionSwap       InstructionKind = "swap"
	InstructionAdd        InstructionKind = "add"
	InstructionSubtract   InstructionKind = "subtract"
	InstructionMultiply   InstructionKind = "multiply"
	InstructionModulo     InstructionKind = "modulo"
	InstructionDivide     InstructionKind = "divide"
	InstructionNegate     InstructionKind = "negate"
	InstructionAnd        InstructionKind = "and"
	InstructionOr         InstructionKind = "or"
	InstructionXor        InstructionKind = "xor"
	InstructionShiftLeft  InstructionKind = "shift_left"
	InstructionShiftRight InstructionKind = "shift_right"
	InstructionReceive    InstructionKind = "receive"
	InstructionSend       InstructionKind = "send"
	InstructionHalt       InstructionKind = "halt"
	InstructionNop        InstructionKind = "nop"
)

type Instruction struct {
	Kind  InstructionKind
	Value int64
	Peer  string
	Line  int
}

func (Instruction) stmt() {}

type Repeat struct {
	Body []Stmt
	Line int
}

func (Repeat) stmt() {}

type WhilePositive struct {
	Body []Stmt
	Line int
}

func (WhilePositive) stmt() {}

type SignBranch struct {
	Negative []Stmt
	Zero     []Stmt
	Positive []Stmt
	Line     int
}

func (SignBranch) stmt() {}
