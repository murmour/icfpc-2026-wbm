package main

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
)

var identifierPattern = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

type sourceLine struct {
	number int
	text   string
}

type parser struct {
	lines []sourceLine
	index int
}

func parseFile(path string) (*Program, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return parseSource(string(data))
}

func parseSource(source string) (*Program, error) {
	var lines []sourceLine
	for index, raw := range strings.Split(source, "\n") {
		text := strings.TrimSpace(raw)
		if comment := strings.Index(text, "#"); comment >= 0 {
			text = strings.TrimSpace(text[:comment])
		}
		if text != "" {
			lines = append(lines, sourceLine{number: index + 1, text: text})
		}
	}

	p := &parser{lines: lines}
	program := &Program{}
	if len(lines) > 0 && strings.HasPrefix(lines[0].text, "program ") {
		fields := strings.Fields(lines[0].text)
		if len(fields) != 2 || !validIdentifier(fields[1]) {
			return nil, p.errorf(lines[0], "expected: program NAME")
		}
		program.Name = fields[1]
		p.index++
	}

	for p.index < len(p.lines) {
		if strings.HasPrefix(p.lines[p.index].text, "pipe ") {
			pipe, err := p.parsePipe()
			if err != nil {
				return nil, err
			}
			program.Pipes = append(program.Pipes, pipe)
			continue
		}
		block, err := p.parseBlock()
		if err != nil {
			return nil, err
		}
		program.Blocks = append(program.Blocks, block)
	}
	if program.Name == "" {
		program.Name = "plumber"
	}
	if err := validateProgram(program); err != nil {
		return nil, err
	}
	return program, nil
}

func (p *parser) parsePipe() (*Pipe, error) {
	line := p.lines[p.index]
	fields := strings.Fields(line.text)
	if (len(fields) != 2 && len(fields) != 3) || fields[0] != "pipe" ||
		!validIdentifier(fields[1]) {
		return nil, p.errorf(line, "expected: pipe NAME [MIN..MAX]")
	}
	const defaultMaximum = 1_000_000
	minSize, maxSize := 2, defaultMaximum
	if len(fields) == 3 {
		lower, upper, found := strings.Cut(fields[2], "..")
		if !found {
			return nil, p.errorf(line, "pipe size must use MIN..MAX syntax")
		}
		var err error
		if lower != "" {
			minSize, err = strconv.Atoi(lower)
			if err != nil {
				return nil, p.errorf(line, "invalid pipe minimum %q", lower)
			}
		}
		if upper != "" {
			maxSize, err = strconv.Atoi(upper)
			if err != nil {
				return nil, p.errorf(line, "invalid pipe maximum %q", upper)
			}
		}
	}
	if minSize < 2 || maxSize < minSize {
		return nil, p.errorf(line, "invalid pipe size range %d..%d", minSize, maxSize)
	}
	p.index++
	return &Pipe{
		Name:    fields[1],
		MinSize: minSize,
		MaxSize: maxSize,
		Line:    line.number,
	}, nil
}

func (p *parser) parseBlock() (*Block, error) {
	line := p.lines[p.index]
	fields := strings.Fields(line.text)
	if len(fields) != 3 || fields[0] != "block" || fields[2] != "{" ||
		!validIdentifier(fields[1]) {
		return nil, p.errorf(line, "expected: block NAME {")
	}
	block := &Block{Name: fields[1], Line: line.number}
	p.index++

	if p.index >= len(p.lines) || p.lines[p.index].text != "forever {" {
		return nil, p.errorf(line, "block %q must contain `forever {`", block.Name)
	}
	p.index++
	body, err := p.parseStatements()
	if err != nil {
		return nil, err
	}
	block.Body = body

	if p.index >= len(p.lines) || p.lines[p.index].text != "}" {
		return nil, p.errorf(line, "unterminated block %q", block.Name)
	}
	p.index++
	return block, nil
}

func (p *parser) parseStatements() ([]Stmt, error) {
	var statements []Stmt
	for p.index < len(p.lines) {
		line := p.lines[p.index]
		if line.text == "}" {
			p.index++
			return statements, nil
		}

		switch line.text {
		case "repeat A {":
			p.index++
			body, err := p.parseStatements()
			if err != nil {
				return nil, err
			}
			statements = append(statements, Repeat{Body: body, Line: line.number})
		case "while positive A {":
			p.index++
			body, err := p.parseStatements()
			if err != nil {
				return nil, err
			}
			statements = append(
				statements,
				WhilePositive{Body: body, Line: line.number},
			)
		case "if sign A {":
			branch, err := p.parseSignBranch(line)
			if err != nil {
				return nil, err
			}
			statements = append(statements, branch)
		default:
			instruction, err := parseInstruction(line)
			if err != nil {
				return nil, err
			}
			statements = append(statements, instruction)
			p.index++
		}
	}
	return nil, p.errorf(sourceLine{number: 0}, "unterminated statement block")
}

func (p *parser) parseSignBranch(line sourceLine) (SignBranch, error) {
	branch := SignBranch{Line: line.number}
	p.index++
	seen := make(map[string]bool)
	for p.index < len(p.lines) {
		clause := p.lines[p.index]
		if clause.text == "}" {
			p.index++
			return branch, nil
		}

		fields := strings.Fields(clause.text)
		if len(fields) != 2 || fields[1] != "{" {
			return SignBranch{}, p.errorf(
				clause,
				"expected negative {, zero {, positive {, or }",
			)
		}
		name := fields[0]
		if name != "negative" && name != "zero" && name != "positive" {
			return SignBranch{}, p.errorf(clause, "invalid sign clause %q", name)
		}
		if seen[name] {
			return SignBranch{}, p.errorf(clause, "duplicate %s clause", name)
		}
		seen[name] = true
		p.index++
		body, err := p.parseStatements()
		if err != nil {
			return SignBranch{}, err
		}
		switch name {
		case "negative":
			branch.Negative = body
		case "zero":
			branch.Zero = body
		case "positive":
			branch.Positive = body
		}
	}
	return SignBranch{}, p.errorf(line, "unterminated sign branch")
}

func parseInstruction(line sourceLine) (Instruction, error) {
	simple := map[string]InstructionKind{
		"B = A":   InstructionCopy,
		"swap":    InstructionSwap,
		"A += B":  InstructionAdd,
		"A -= B":  InstructionSubtract,
		"A *= B":  InstructionMultiply,
		"A %= B":  InstructionModulo,
		"A /= B":  InstructionDivide,
		"A = -A":  InstructionNegate,
		"A &= B":  InstructionAnd,
		"A |= B":  InstructionOr,
		"A ^= B":  InstructionXor,
		"A <<= B": InstructionShiftLeft,
		"A >>= B": InstructionShiftRight,
		"halt":    InstructionHalt,
		"nop":     InstructionNop,
	}
	if kind, ok := simple[line.text]; ok {
		return Instruction{Kind: kind, Line: line.number}, nil
	}

	if strings.HasPrefix(line.text, "A = recv ") {
		peer := strings.TrimSpace(strings.TrimPrefix(line.text, "A = recv "))
		if !validEndpoint(peer) {
			return Instruction{}, pError(line, "invalid receive endpoint %q", peer)
		}
		return Instruction{Kind: InstructionReceive, Peer: peer, Line: line.number}, nil
	}
	if strings.HasPrefix(line.text, "send ") {
		fields := strings.Fields(line.text)
		if len(fields) != 2 || !validEndpoint(fields[1]) {
			return Instruction{}, pError(line, "expected: send BLOCK")
		}
		return Instruction{Kind: InstructionSend, Peer: fields[1], Line: line.number}, nil
	}
	if strings.HasPrefix(line.text, "A = ") {
		raw := strings.TrimSpace(strings.TrimPrefix(line.text, "A = "))
		value, err := strconv.ParseInt(raw, 10, 64)
		if err != nil {
			return Instruction{}, pError(line, "unsupported assignment %q", line.text)
		}
		return Instruction{
			Kind:  InstructionLoad,
			Value: value,
			Line:  line.number,
		}, nil
	}
	return Instruction{}, pError(line, "unsupported instruction %q", line.text)
}

func validateProgram(program *Program) error {
	blocks := make(map[string]*Block)
	for _, block := range program.Blocks {
		if _, exists := blocks[block.Name]; exists {
			return fmt.Errorf("line %d: duplicate block %q", block.Line, block.Name)
		}
		blocks[block.Name] = block
	}
	pipes := make(map[string]*Pipe)
	for _, pipe := range program.Pipes {
		if blocks[pipe.Name] != nil {
			return fmt.Errorf(
				"line %d: pipe %q conflicts with a block",
				pipe.Line,
				pipe.Name,
			)
		}
		if _, exists := pipes[pipe.Name]; exists {
			return fmt.Errorf("line %d: duplicate pipe %q", pipe.Line, pipe.Name)
		}
		pipes[pipe.Name] = pipe
	}
	inputReader := ""
	for _, block := range program.Blocks {
		if err := validateStatements(block, block.Body, blocks, pipes); err != nil {
			return err
		}
		if statementsUseEndpoint(block.Body, InstructionReceive, "input") {
			if inputReader != "" && inputReader != block.Name {
				return fmt.Errorf(
					"blocks %s and %s both receive from input",
					inputReader,
					block.Name,
				)
			}
			inputReader = block.Name
		}
	}
	return nil
}

func statementsUseEndpoint(statements []Stmt, kind InstructionKind, endpoint string) bool {
	for _, statement := range statements {
		switch value := statement.(type) {
		case Instruction:
			if value.Kind == kind && value.Peer == endpoint {
				return true
			}
		case Repeat:
			if statementsUseEndpoint(value.Body, kind, endpoint) {
				return true
			}
		case WhilePositive:
			if statementsUseEndpoint(value.Body, kind, endpoint) {
				return true
			}
		case SignBranch:
			if statementsUseEndpoint(value.Negative, kind, endpoint) ||
				statementsUseEndpoint(value.Zero, kind, endpoint) ||
				statementsUseEndpoint(value.Positive, kind, endpoint) {
				return true
			}
		}
	}
	return false
}

func validateStatements(
	block *Block,
	statements []Stmt,
	blocks map[string]*Block,
	pipes map[string]*Pipe,
) error {
	for _, statement := range statements {
		switch value := statement.(type) {
		case Instruction:
			switch value.Kind {
			case InstructionReceive:
				if value.Peer == "output" {
					return fmt.Errorf("line %d: cannot receive from output", value.Line)
				}
				if value.Peer != "input" && blocks[value.Peer] == nil &&
					pipes[value.Peer] == nil {
					return fmt.Errorf("line %d: unknown endpoint %q", value.Line, value.Peer)
				}
			case InstructionSend:
				if value.Peer == "input" {
					return fmt.Errorf("line %d: cannot send to input", value.Line)
				}
				if value.Peer != "output" && blocks[value.Peer] == nil &&
					pipes[value.Peer] == nil {
					return fmt.Errorf("line %d: unknown endpoint %q", value.Line, value.Peer)
				}
			}
		case Repeat:
			if err := validateStatements(block, value.Body, blocks, pipes); err != nil {
				return err
			}
		case WhilePositive:
			if len(value.Body) == 0 {
				return fmt.Errorf("line %d: empty while loop", value.Line)
			}
			if err := validateStatements(block, value.Body, blocks, pipes); err != nil {
				return err
			}
		case SignBranch:
			for _, body := range [][]Stmt{value.Negative, value.Zero, value.Positive} {
				if err := validateStatements(block, body, blocks, pipes); err != nil {
					return err
				}
			}
		}
	}
	return nil
}

func validIdentifier(value string) bool {
	return identifierPattern.MatchString(value) &&
		value != "input" &&
		value != "output"
}

func validEndpoint(value string) bool {
	return value == "input" || value == "output" || validIdentifier(value)
}

func (p *parser) errorf(line sourceLine, format string, args ...any) error {
	return pError(line, format, args...)
}

func pError(line sourceLine, format string, args ...any) error {
	if line.number == 0 {
		return fmt.Errorf(format, args...)
	}
	return fmt.Errorf("line %d: %s", line.number, fmt.Sprintf(format, args...))
}
