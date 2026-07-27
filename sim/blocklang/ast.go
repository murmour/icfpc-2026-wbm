package main

type Program struct {
	Name    string
	Ports   []Port
	Body    []Stmt
	Tests   []Test
	Forever bool
}

type Port struct {
	Name      string
	Direction string
	Side      string
	Offset    int
	MinLength int
	MaxLength int
}

type Test struct {
	Name      string
	Inputs    map[string][]int64
	Expected  map[string][]int64
	Loopbacks map[string]string
}

type Stmt interface {
	stmt()
}

type Instruction struct {
	Line int
	Code string
	Port string
	Kind string
}

func (Instruction) stmt() {}

type Repeat struct {
	Line        int
	Body        []Stmt
	UseBackpack bool
}

func (Repeat) stmt() {}

type WhilePositive struct {
	Line int
	Body []Stmt
}

func (WhilePositive) stmt() {}

type SignBranch struct {
	Line     int
	Negative []Stmt
	Zero     []Stmt
	Positive []Stmt
}

func (SignBranch) stmt() {}
