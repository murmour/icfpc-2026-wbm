package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type sourceLine struct {
	Number int
	Text   string
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
		line := strings.TrimSpace(raw)
		if comment := strings.Index(line, "#"); comment >= 0 {
			line = strings.TrimSpace(line[:comment])
		}
		if line == "" {
			continue
		}
		lines = append(lines, sourceLine{Number: index + 1, Text: line})
	}

	p := &parser{lines: lines}
	program := &Program{}
	for p.index < len(p.lines) {
		line := p.lines[p.index]
		fields := strings.Fields(line.Text)
		switch fields[0] {
		case "block":
			if len(fields) != 2 {
				return nil, p.errorf(line, "expected: block NAME")
			}
			if program.Name != "" {
				return nil, p.errorf(line, "duplicate block declaration")
			}
			program.Name = fields[1]
			p.index++
		case "input", "output":
			port, parseErr := p.parsePort(line, fields)
			if parseErr != nil {
				return nil, parseErr
			}
			program.Ports = append(program.Ports, port)
			p.index++
		case "forever":
			if line.Text != "forever {" {
				return nil, p.errorf(line, "expected: forever {")
			}
			if program.Forever {
				return nil, p.errorf(line, "duplicate forever block")
			}
			p.index++
			body, parseErr := p.parseStatements()
			if parseErr != nil {
				return nil, parseErr
			}
			program.Body = body
			program.Forever = true
		case "test":
			test, parseErr := p.parseTest(line, fields)
			if parseErr != nil {
				return nil, parseErr
			}
			program.Tests = append(program.Tests, test)
		default:
			return nil, p.errorf(line, "unexpected top-level declaration %q", fields[0])
		}
	}

	if program.Name == "" {
		return nil, fmt.Errorf("missing block declaration")
	}
	if !program.Forever {
		return nil, fmt.Errorf("missing forever block")
	}
	return program, nil
}

func (p *parser) parsePort(line sourceLine, fields []string) (Port, error) {
	if len(fields) != 3 && len(fields) != 5 && len(fields) != 6 {
		return Port{}, p.errorf(line, "expected: %s NAME auto [MIN_LENGTH MAX_LENGTH], or %s NAME SIDE OFFSET MIN_LENGTH MAX_LENGTH", fields[0], fields[0])
	}
	port := Port{
		Name:      fields[1],
		Direction: fields[0],
		Side:      fields[2],
		Offset:    -1,
		MinLength: 2,
		MaxLength: 64,
	}
	if len(fields) == 3 || len(fields) == 5 {
		if port.Side != "auto" {
			return Port{}, p.errorf(line, "port declaration without an offset must use auto")
		}
		if len(fields) == 5 {
			minLength, minErr := strconv.Atoi(fields[3])
			maxLength, maxErr := strconv.Atoi(fields[4])
			if minErr != nil || maxErr != nil || minLength < 2 || maxLength < minLength {
				return Port{}, p.errorf(line, "invalid port length range")
			}
			port.MinLength = minLength
			port.MaxLength = maxLength
		}
		return port, nil
	}
	switch port.Side {
	case "top", "bottom", "left", "right":
	default:
		return Port{}, p.errorf(line, "invalid port side %q", port.Side)
	}
	values := []*int{&port.Offset, &port.MinLength, &port.MaxLength}
	for index, target := range values {
		value, err := strconv.Atoi(fields[index+3])
		if err != nil {
			return Port{}, p.errorf(line, "invalid integer %q", fields[index+3])
		}
		*target = value
	}
	if port.Offset < 0 || port.MinLength < 2 || port.MaxLength < port.MinLength {
		return Port{}, p.errorf(line, "invalid port offset or length range")
	}
	return port, nil
}

func (p *parser) parseStatements() ([]Stmt, error) {
	var statements []Stmt
	for p.index < len(p.lines) {
		line := p.lines[p.index]
		if line.Text == "}" {
			p.index++
			return statements, nil
		}
		switch line.Text {
		case "repeat A {":
			p.index++
			body, err := p.parseStatements()
			if err != nil {
				return nil, err
			}
			statements = append(statements, Repeat{Line: line.Number, Body: body})
		case "repeat backpack {":
			p.index++
			body, err := p.parseStatements()
			if err != nil {
				return nil, err
			}
			statements = append(statements, Repeat{
				Line:        line.Number,
				Body:        body,
				UseBackpack: true,
			})
		case "while positive A {":
			p.index++
			body, err := p.parseStatements()
			if err != nil {
				return nil, err
			}
			if len(body) == 0 {
				return nil, p.errorf(line, "empty while loop")
			}
			statements = append(statements, WhilePositive{
				Line: line.Number,
				Body: body,
			})
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
	return nil, fmt.Errorf("unterminated statement block")
}

func (p *parser) parseSignBranch(line sourceLine) (SignBranch, error) {
	branch := SignBranch{Line: line.Number}
	p.index++
	seen := make(map[string]bool)
	for p.index < len(p.lines) {
		clause := p.lines[p.index]
		if clause.Text == "}" {
			p.index++
			return branch, nil
		}
		fields := strings.Fields(clause.Text)
		if len(fields) != 2 || fields[1] != "{" {
			return SignBranch{}, p.errorf(clause, "expected negative {, zero {, positive {, or }")
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
	text := line.Text
	simple := map[string]string{
		"B = A":              "M",
		"swap":               "W",
		"A += B":             "+",
		"A -= B":             "-",
		"A *= B":             "*",
		"A %= B":             "%",
		"A /= B":             "/",
		"A = -A":             "N",
		"A &= B":             "&",
		"A |= B":             "|",
		"A ^= B":             "~",
		"A <<= B":            "{",
		"A >>= B":            "}",
		"decrement backpack": "m",
		"halt":               "H",
		"nop":                " ",
	}
	if code, ok := simple[text]; ok {
		return Instruction{Line: line.Number, Code: code}, nil
	}
	if strings.HasPrefix(text, "raw ") {
		code := strings.TrimSpace(strings.TrimPrefix(text, "raw "))
		if code == "" {
			return Instruction{}, fmt.Errorf("line %d: empty raw instruction", line.Number)
		}
		for _, char := range code {
			if !strings.ContainsRune("0123456789MW+-*N&|~{}", char) {
				return Instruction{}, fmt.Errorf(
					"line %d: unsupported raw instruction %q",
					line.Number,
					char,
				)
			}
		}
		return Instruction{Line: line.Number, Code: code}, nil
	}
	if strings.HasPrefix(text, "A = recv ") {
		port := strings.TrimSpace(strings.TrimPrefix(text, "A = recv "))
		if port == "" {
			return Instruction{}, fmt.Errorf("line %d: missing input port", line.Number)
		}
		if port == "any" {
			return Instruction{Line: line.Number, Code: "R", Port: "*", Kind: "input_any"}, nil
		}
		return Instruction{Line: line.Number, Code: "r", Port: port, Kind: "input"}, nil
	}
	if strings.HasPrefix(text, "A = query ") {
		port := strings.TrimSpace(strings.TrimPrefix(text, "A = query "))
		if port == "" {
			return Instruction{}, fmt.Errorf("line %d: missing input port", line.Number)
		}
		return Instruction{Line: line.Number, Code: "q", Port: port, Kind: "input"}, nil
	}
	if strings.HasPrefix(text, "query ") {
		port := strings.TrimSpace(strings.TrimPrefix(text, "query "))
		if port == "" {
			return Instruction{}, fmt.Errorf("line %d: missing input port", line.Number)
		}
		return Instruction{Line: line.Number, Code: "q", Port: port, Kind: "input"}, nil
	}
	if strings.HasPrefix(text, "send ") {
		fields := strings.Fields(text)
		if len(fields) != 2 {
			return Instruction{}, fmt.Errorf("line %d: expected: send PORT", line.Number)
		}
		return Instruction{Line: line.Number, Code: "s", Port: fields[1], Kind: "output"}, nil
	}
	if text == "broadcast" {
		return Instruction{Line: line.Number, Code: "S", Port: "*", Kind: "broadcast"}, nil
	}
	if strings.HasPrefix(text, "broadcast ") {
		fields := strings.Fields(text)
		if len(fields) != 2 {
			return Instruction{}, fmt.Errorf("line %d: expected: broadcast PORT", line.Number)
		}
		if fields[1] == "all" {
			return Instruction{Line: line.Number, Code: "S", Kind: "broadcast_all"}, nil
		}
		return Instruction{Line: line.Number, Code: "S", Port: fields[1], Kind: "broadcast"}, nil
	}
	if strings.HasPrefix(text, "A = ") {
		valueText := strings.TrimSpace(strings.TrimPrefix(text, "A = "))
		value, err := strconv.ParseInt(valueText, 10, 64)
		if err != nil {
			return Instruction{}, fmt.Errorf("line %d: unsupported assignment %q", line.Number, text)
		}
		code, err := literalCode(value)
		if err != nil {
			return Instruction{}, fmt.Errorf("line %d: %w", line.Number, err)
		}
		return Instruction{Line: line.Number, Code: code}, nil
	}
	return Instruction{}, fmt.Errorf("line %d: unsupported instruction %q", line.Number, text)
}

func literalCode(value int64) (string, error) {
	if value < 0 {
		if value == -1<<63 {
			return "", fmt.Errorf("minimum int64 literal is not supported")
		}
		positive, err := literalCode(-value)
		if err != nil {
			return "", err
		}
		return positive + "N", nil
	}
	digits := strconv.FormatInt(value, 10)
	reversed := reverse(digits)
	if _, err := strconv.ParseInt(reversed, 10, 64); err != nil {
		return "", fmt.Errorf("literal %d is invalid when traversed backward", value)
	}
	return "`" + digits + "`", nil
}

func reverse(value string) string {
	bytes := []byte(value)
	for left, right := 0, len(bytes)-1; left < right; left, right = left+1, right-1 {
		bytes[left], bytes[right] = bytes[right], bytes[left]
	}
	return string(bytes)
}

func (p *parser) parseTest(line sourceLine, fields []string) (Test, error) {
	if len(fields) != 3 || fields[2] != "{" {
		return Test{}, p.errorf(line, "expected: test NAME {")
	}
	test := Test{
		Name:      fields[1],
		Inputs:    make(map[string][]int64),
		Expected:  make(map[string][]int64),
		Loopbacks: make(map[string]string),
	}
	p.index++
	for p.index < len(p.lines) {
		entry := p.lines[p.index]
		if entry.Text == "}" {
			p.index++
			return test, nil
		}
		before, after, ok := strings.Cut(entry.Text, ":")
		if !ok {
			return Test{}, p.errorf(entry, "expected ':' in test entry")
		}
		header := strings.Fields(strings.TrimSpace(before))
		if len(header) != 2 {
			return Test{}, p.errorf(entry, "expected test entry kind and port")
		}
		switch header[0] {
		case "input", "expected":
			var values []int64
			for _, raw := range strings.Fields(after) {
				value, err := strconv.ParseInt(raw, 10, 64)
				if err != nil {
					return Test{}, p.errorf(entry, "invalid test value %q", raw)
				}
				values = append(values, value)
			}
			if header[0] == "input" {
				test.Inputs[header[1]] = values
			} else {
				test.Expected[header[1]] = values
			}
		case "loopback":
			target := strings.TrimSpace(after)
			if target == "" {
				return Test{}, p.errorf(entry, "missing loopback target")
			}
			test.Loopbacks[header[1]] = target
		default:
			return Test{}, p.errorf(entry, "invalid test entry %q", header[0])
		}
		p.index++
	}
	return Test{}, p.errorf(line, "unterminated test")
}

func (p *parser) errorf(line sourceLine, format string, args ...any) error {
	return fmt.Errorf("line %d: %s", line.Number, fmt.Sprintf(format, args...))
}
