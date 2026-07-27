package main

import (
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
)

type Point struct {
	X int
	Y int
}

type operationRef struct {
	Point
	Port string
	Kind string
	Line int
}

type box struct {
	Width    int
	Height   int
	Baseline int
	Cells    map[Point]byte
	Refs     []operationRef
}

type compiler struct {
	repeatDepth   int
	sequenceDepth int
	foldTopLevel  bool
	portDepth     map[string]int
	directPorts   map[string]bool
}

func compileProgram(program *Program) (*BlockDef, error) {
	if err := validateProgram(program); err != nil {
		return nil, err
	}
	room, ports, err := compileGeometry(program, true, true)
	if err != nil {
		room, ports, err = compileGeometry(program, true, false)
	}
	if err != nil {
		room, ports, err = compileGeometry(program, false, true)
	}
	if err != nil {
		room, ports, err = compileGeometry(program, false, false)
	}
	if err != nil {
		return nil, err
	}

	interior := make([]string, room.Height)
	for y := 0; y < room.Height; y++ {
		row := make([]byte, room.Width)
		for x := range row {
			row[x] = ' '
		}
		for x := 0; x < room.Width; x++ {
			if value, ok := room.Cells[Point{X: x, Y: y}]; ok {
				row[x] = value
			}
		}
		interior[y] = string(row)
	}

	portDefs := make(map[string]PortDef)
	for _, port := range ports {
		portDefs[port.Name] = PortDef{
			Type:        port.Direction,
			Side:        port.Side,
			OffsetRange: []int{port.Offset, port.Offset},
			LengthRange: []int{port.MinLength, port.MaxLength},
		}
	}

	tests := make([]TestDef, len(program.Tests))
	for index, test := range program.Tests {
		tests[index] = TestDef{
			Name:      test.Name,
			Inputs:    test.Inputs,
			Expected:  test.Expected,
			Loopbacks: test.Loopbacks,
		}
	}
	return &BlockDef{
		Name:     program.Name,
		Size:     strconv.Itoa(room.Width) + "x" + strconv.Itoa(room.Height),
		Interior: interior,
		Ports:    portDefs,
		Tests:    tests,
	}, nil
}

func compileGeometry(
	program *Program,
	directAllPorts bool,
	foldTopLevel bool,
) (box, []Port, error) {
	c := &compiler{
		portDepth:    make(map[string]int),
		directPorts:  make(map[string]bool),
		foldTopLevel: foldTopLevel,
	}
	directionIndex := map[string]int{"input": 0, "output": 0}
	for _, port := range program.Ports {
		c.portDepth[port.Name] = 1 + directionIndex[port.Direction]*6
		directionIndex[port.Direction]++
	}
	for _, port := range program.Ports {
		c.directPorts[port.Name] =
			directAllPorts || directionIndex[port.Direction] == 1
	}
	body, err := c.compileSequence(program.Body)
	if err != nil {
		return box{}, nil, err
	}
	room, err := wrapForever(body)
	if err != nil {
		return box{}, nil, err
	}
	if os.Getenv("BLOCKLANG_DEBUG_GEOMETRY") != "" {
		fmt.Fprintf(os.Stderr, "room=%dx%d\n", room.Width, room.Height)
		for _, ref := range room.Refs {
			fmt.Fprintf(
				os.Stderr,
				"%s %s (%d,%d)\n",
				ref.Kind,
				ref.Port,
				ref.X,
				ref.Y,
			)
		}
	}

	ports := append([]Port(nil), program.Ports...)
	if !directAllPorts && assignPortBands(ports, room) {
		if err := validatePorts(ports, room); err == nil {
			return room, ports, nil
		}
	}
	if err := assignAutoPorts(ports, room); err != nil {
		return box{}, nil, err
	}
	if err := validatePorts(ports, room); err != nil {
		return box{}, nil, err
	}
	return room, ports, nil
}

func assignPortBands(ports []Port, room box) bool {
	used := make(map[string]bool)
	for index := range ports {
		if ports[index].Side != "auto" {
			used[ports[index].Side+":"+strconv.Itoa(ports[index].Offset)] = true
			continue
		}
		totalY := 0
		count := 0
		for _, ref := range room.Refs {
			if ref.Port == ports[index].Name {
				totalY += ref.Y
				count++
			}
		}
		if count == 0 {
			return false
		}
		side := "left"
		if ports[index].Direction == "output" {
			side = "right"
		}
		offset := totalY / count
		for offset < room.Height {
			key := side + ":" + strconv.Itoa(offset)
			if !used[key] {
				ports[index].Side = side
				ports[index].Offset = offset
				used[key] = true
				break
			}
			offset++
		}
		if ports[index].Side == "auto" {
			return false
		}
	}
	return directionBindingsMatch(ports, room, "input") &&
		directionBindingsMatch(ports, room, "output")
}

func validateProgram(program *Program) error {
	directions := make(map[string]string)
	for _, port := range program.Ports {
		if _, exists := directions[port.Name]; exists {
			return fmt.Errorf("duplicate port %q", port.Name)
		}
		directions[port.Name] = port.Direction
	}

	testNames := make(map[string]bool)
	for _, test := range program.Tests {
		if testNames[test.Name] {
			return fmt.Errorf("duplicate test %q", test.Name)
		}
		testNames[test.Name] = true
		for port := range test.Inputs {
			if directions[port] != "input" {
				return fmt.Errorf("test %q: input %q is not an input port", test.Name, port)
			}
		}
		for port := range test.Expected {
			if directions[port] != "output" {
				return fmt.Errorf("test %q: expected %q is not an output port", test.Name, port)
			}
		}
		for output, input := range test.Loopbacks {
			if directions[output] != "output" {
				return fmt.Errorf("test %q: loopback source %q is not an output port", test.Name, output)
			}
			if directions[input] != "input" {
				return fmt.Errorf("test %q: loopback target %q is not an input port", test.Name, input)
			}
		}
	}
	return nil
}

func (c *compiler) compileSequence(statements []Stmt) (box, error) {
	depth := c.sequenceDepth
	c.sequenceDepth++
	defer func() {
		c.sequenceDepth--
	}()
	if len(statements) == 0 {
		return blankBox(), nil
	}
	parts := make([]box, 0, len(statements))
	for _, statement := range statements {
		var compiled box
		var err error
		switch value := statement.(type) {
		case Instruction:
			compiled = c.instructionBox(value)
		case Repeat:
			if c.repeatDepth != 0 {
				return box{}, fmt.Errorf("line %d: nested repeat is not supported", value.Line)
			}
			c.repeatDepth++
			body, compileErr := c.compileSequence(value.Body)
			c.repeatDepth--
			if compileErr != nil {
				return box{}, compileErr
			}
			compiled, err = repeatBox(body, !value.UseBackpack)
		case WhilePositive:
			body, compileErr := c.compileSequence(value.Body)
			if compileErr != nil {
				return box{}, compileErr
			}
			compiled, err = whilePositiveBox(body)
		case SignBranch:
			negative, compileErr := c.compileSequence(value.Negative)
			if compileErr != nil {
				return box{}, compileErr
			}
			zero, compileErr := c.compileSequence(value.Zero)
			if compileErr != nil {
				return box{}, compileErr
			}
			positive, compileErr := c.compileSequence(value.Positive)
			if compileErr != nil {
				return box{}, compileErr
			}
			compiled, err = signBox(negative, zero, positive)
		default:
			return box{}, fmt.Errorf("unsupported statement %T", statement)
		}
		if err != nil {
			return box{}, err
		}
		parts = append(parts, compiled)
	}
	if depth == 0 && c.foldTopLevel {
		return foldTopLevelSequence(parts)
	}
	return sequenceBox(parts)
}

func foldTopLevelSequence(parts []box) (box, error) {
	totalWidth := 0
	targetWidth := 0
	for _, part := range parts {
		totalWidth += part.Width
		targetWidth = max(targetWidth, part.Width)
	}
	if totalWidth <= targetWidth+6 {
		return sequenceBox(parts)
	}

	var rows []box
	var current []box
	currentWidth := 0
	for _, part := range parts {
		if len(current) != 0 && currentWidth+part.Width > targetWidth {
			row, err := sequenceBox(current)
			if err != nil {
				return box{}, err
			}
			rows = append(rows, row)
			current = nil
			currentWidth = 0
		}
		current = append(current, part)
		currentWidth += part.Width
	}
	if len(current) != 0 {
		row, err := sequenceBox(current)
		if err != nil {
			return box{}, err
		}
		rows = append(rows, row)
	}
	if len(rows) == 1 {
		return rows[0], nil
	}
	return foldedRowsBox(rows)
}

func foldedRowsBox(rows []box) (box, error) {
	rowTop := make([]int, len(rows))
	rowX := make([]int, len(rows))
	usedBackticks := make(map[int]bool)
	maxRight := 0
	height := 0
	for index, row := range rows {
		if index != 0 {
			rowTop[index] = height + 1
		}
		shift := 1
		for {
			conflict := false
			for point, value := range row.Cells {
				if value == '`' && usedBackticks[shift+point.X] {
					conflict = true
					break
				}
			}
			if !conflict {
				break
			}
			shift++
		}
		rowX[index] = shift
		for point, value := range row.Cells {
			if value == '`' {
				usedBackticks[shift+point.X] = true
			}
		}
		maxRight = max(maxRight, shift+row.Width)
		height = rowTop[index] + row.Height
	}
	mergeX := maxRight + 1
	firstBaseline := rowTop[0] + rows[0].Baseline
	last := len(rows) - 1
	lastBaseline := rowTop[last] + rows[last].Baseline
	result := box{
		Width:    mergeX + 1,
		Height:   height,
		Baseline: firstBaseline,
		Cells:    make(map[Point]byte),
	}

	for index, row := range rows {
		if err := overlay(&result, row, rowX[index], rowTop[index]); err != nil {
			return box{}, err
		}
		baseline := rowTop[index] + row.Baseline
		result.Cells[Point{X: 0, Y: baseline}] = '>'
		if index == last {
			continue
		}
		exitX := rowX[index] + row.Width
		connectorY := rowTop[index] + row.Height
		result.Cells[Point{X: exitX, Y: baseline}] = 'v'
		result.Cells[Point{X: exitX, Y: connectorY}] = '<'
		result.Cells[Point{X: 0, Y: connectorY}] = 'v'
	}

	result.Cells[Point{X: mergeX, Y: lastBaseline}] = '^'
	result.Cells[Point{X: mergeX, Y: firstBaseline}] = '>'
	return result, nil
}

func blankBox() box {
	return box{Width: 1, Height: 1, Cells: make(map[Point]byte)}
}

func (c *compiler) instructionBox(instruction Instruction) box {
	if instruction.Port != "" && instruction.Kind != "broadcast" && instruction.Kind != "input_any" {
		return c.portInstructionBox(instruction)
	}
	result := box{
		Width:  len(instruction.Code),
		Height: 1,
		Cells:  make(map[Point]byte),
	}
	if result.Width == 0 {
		result.Width = 1
	}
	for index := 0; index < len(instruction.Code); index++ {
		value := instruction.Code[index]
		if value != ' ' {
			result.Cells[Point{X: index, Y: 0}] = value
		}
	}
	if instruction.Port != "" {
		for index := 0; index < len(instruction.Code); index++ {
			if instruction.Code[index] == 'r' || instruction.Code[index] == 'R' ||
				instruction.Code[index] == 's' || instruction.Code[index] == 'S' ||
				instruction.Code[index] == 'q' {
				result.Refs = append(result.Refs, operationRef{
					Point: Point{X: index, Y: 0},
					Port:  instruction.Port,
					Kind:  instruction.Kind,
					Line:  instruction.Line,
				})
			}
		}
	}
	return result
}

func (c *compiler) portInstructionBox(instruction Instruction) box {
	if c.directPorts[instruction.Port] {
		return box{
			Width:  1,
			Height: 1,
			Cells: map[Point]byte{
				{X: 0, Y: 0}: instruction.Code[0],
			},
			Refs: []operationRef{{
				Point: Point{X: 0, Y: 0},
				Port:  instruction.Port,
				Kind:  instruction.Kind,
				Line:  instruction.Line,
			}},
		}
	}
	depth, exists := c.portDepth[instruction.Port]
	if !exists {
		depth = 1
	}
	result := box{
		Width:    3,
		Height:   depth + 1,
		Baseline: 0,
		Cells:    make(map[Point]byte),
	}
	result.Cells[Point{X: 0, Y: 0}] = 'v'
	result.Cells[Point{X: 2, Y: 0}] = '>'
	result.Cells[Point{X: 0, Y: depth}] = '>'
	result.Cells[Point{X: 1, Y: depth}] = instruction.Code[0]
	result.Cells[Point{X: 2, Y: depth}] = '^'
	result.Refs = append(result.Refs, operationRef{
		Point: Point{X: 1, Y: depth},
		Port:  instruction.Port,
		Kind:  instruction.Kind,
		Line:  instruction.Line,
	})
	return result
}

func sequenceBox(parts []box) (box, error) {
	if len(parts) == 0 {
		return blankBox(), nil
	}
	baseline := 0
	below := 0
	width := 0
	for _, part := range parts {
		if part.Baseline > baseline {
			baseline = part.Baseline
		}
		partBelow := part.Height - part.Baseline - 1
		if partBelow > below {
			below = partBelow
		}
		width += part.Width
	}
	result := box{
		Width:    width,
		Height:   baseline + below + 1,
		Baseline: baseline,
		Cells:    make(map[Point]byte),
	}
	x := 0
	for _, part := range parts {
		y := baseline - part.Baseline
		if err := overlay(&result, part, x, y); err != nil {
			return box{}, err
		}
		x += part.Width
	}
	return result, nil
}

func signBox(negative, zero, positive box) (box, error) {
	if equivalentBoxes(zero, positive) {
		return negativeNonnegativeBox(negative, zero)
	}
	negativeTop := 0
	zeroTop := negative.Height + 1
	positiveTop := zeroTop + zero.Height + 1
	center := zeroTop + zero.Baseline
	negativeLane := negativeTop + negative.Baseline
	positiveLane := positiveTop + positive.Baseline
	maxWidth := max(negative.Width, max(zero.Width, positive.Width))
	mergeX := maxWidth + 2

	result := box{
		Width:    mergeX + 1,
		Height:   positiveTop + positive.Height,
		Baseline: center,
		Cells:    make(map[Point]byte),
	}
	result.Cells[Point{X: 0, Y: center}] = 'X'
	result.Cells[Point{X: 0, Y: negativeLane}] = '>'
	result.Cells[Point{X: 0, Y: positiveLane}] = '>'

	if err := overlay(&result, negative, 1, negativeTop); err != nil {
		return box{}, err
	}
	if err := overlay(&result, zero, 1, zeroTop); err != nil {
		return box{}, err
	}
	if err := overlay(&result, positive, 1, positiveTop); err != nil {
		return box{}, err
	}

	result.Cells[Point{X: mergeX, Y: negativeLane}] = 'v'
	result.Cells[Point{X: mergeX, Y: center}] = '>'
	result.Cells[Point{X: mergeX, Y: positiveLane}] = '^'
	return result, nil
}

func equivalentBoxes(left, right box) bool {
	if left.Width != right.Width ||
		left.Height != right.Height ||
		left.Baseline != right.Baseline ||
		len(left.Cells) != len(right.Cells) ||
		len(left.Refs) != len(right.Refs) {
		return false
	}
	for point, value := range left.Cells {
		if right.Cells[point] != value {
			return false
		}
	}
	for index, ref := range left.Refs {
		other := right.Refs[index]
		if ref.Point != other.Point ||
			ref.Port != other.Port ||
			ref.Kind != other.Kind {
			return false
		}
	}
	return true
}

func negativeNonnegativeBox(negative, nonnegative box) (box, error) {
	negativeX, negativeY := 1, 0
	center := negative.Height + 1
	nonnegativeX, nonnegativeY := 2, center+1
	negativeLane := negativeY + negative.Baseline
	nonnegativeLane := nonnegativeY + nonnegative.Baseline
	mergeX := max(
		negativeX+negative.Width,
		nonnegativeX+nonnegative.Width,
	) + 1
	result := box{
		Width:    mergeX + 1,
		Height:   nonnegativeY + nonnegative.Height,
		Baseline: center,
		Cells:    make(map[Point]byte),
	}
	result.Cells[Point{X: 0, Y: center}] = 'X'
	result.Cells[Point{X: 0, Y: negativeLane}] = '>'
	result.Cells[Point{X: 0, Y: nonnegativeLane}] = '>'
	result.Cells[Point{X: 1, Y: center}] = 'v'
	result.Cells[Point{X: 1, Y: nonnegativeLane}] = '>'
	result.Cells[Point{X: mergeX, Y: negativeLane}] = 'v'
	result.Cells[Point{X: mergeX, Y: center}] = '>'
	result.Cells[Point{X: mergeX, Y: nonnegativeLane}] = '^'
	if err := overlay(&result, negative, negativeX, negativeY); err != nil {
		return box{}, err
	}
	if err := overlay(
		&result,
		nonnegative,
		nonnegativeX,
		nonnegativeY,
	); err != nil {
		return box{}, err
	}
	return result, nil
}

func repeatBox(body box, initialize bool) (box, error) {
	bodyX := 2
	bodyTop := 1
	bodyLane := bodyTop + body.Baseline
	bodyLastX := bodyX + body.Width - 1
	decrementX := bodyLastX + 1
	testX := decrementX + 1
	mergeX := testX + 1
	returnY := bodyTop + body.Height

	result := box{
		Width:    mergeX + 1,
		Height:   returnY + 1,
		Baseline: 0,
		Cells:    make(map[Point]byte),
	}
	if initialize {
		result.Cells[Point{X: 0, Y: 0}] = 'b'
	}
	result.Cells[Point{X: 1, Y: 0}] = 'd'
	result.Cells[Point{X: 1, Y: bodyLane}] = '>'
	result.Cells[Point{X: decrementX, Y: bodyLane}] = 'm'
	result.Cells[Point{X: testX, Y: bodyLane}] = 'd'
	result.Cells[Point{X: mergeX, Y: bodyLane}] = '^'
	result.Cells[Point{X: mergeX, Y: 0}] = '>'
	result.Cells[Point{X: testX, Y: returnY}] = '<'
	result.Cells[Point{X: 1, Y: returnY}] = '^'
	if err := overlay(&result, body, bodyX, bodyTop); err != nil {
		return box{}, err
	}
	return result, nil
}

func whilePositiveBox(body box) (box, error) {
	bodyX := 2
	bodyTop := 2
	bodyLane := bodyTop + body.Baseline
	turnX := bodyX + body.Width
	mergeX := turnX + 1
	returnY := bodyTop + body.Height

	result := box{
		Width:    mergeX + 1,
		Height:   returnY + 1,
		Baseline: 1,
		Cells:    make(map[Point]byte),
	}

	// Negative exits over the top, zero exits straight, and positive turns
	// down into the body. The lower track returns to X from the west.
	result.Cells[Point{X: 0, Y: 1}] = '>'
	result.Cells[Point{X: 1, Y: 1}] = 'X'
	result.Cells[Point{X: 1, Y: 0}] = '>'
	result.Cells[Point{X: mergeX, Y: 0}] = 'v'
	result.Cells[Point{X: mergeX, Y: 1}] = '>'

	result.Cells[Point{X: 1, Y: bodyLane}] = '>'
	result.Cells[Point{X: turnX, Y: bodyLane}] = 'v'
	result.Cells[Point{X: turnX, Y: returnY}] = '<'
	result.Cells[Point{X: 0, Y: returnY}] = '^'
	if err := overlay(&result, body, bodyX, bodyTop); err != nil {
		return box{}, err
	}
	return result, nil
}

func wrapForever(body box) (box, error) {
	bodyX := 2
	baseline := body.Baseline
	turnX := bodyX + body.Width
	returnY := body.Height
	result := box{
		Width:    turnX + 1,
		Height:   returnY + 1,
		Baseline: baseline,
		Cells:    make(map[Point]byte),
	}
	result.Cells[Point{X: 0, Y: baseline}] = '>'
	result.Cells[Point{X: 1, Y: baseline}] = '@'
	result.Cells[Point{X: turnX, Y: baseline}] = 'v'
	result.Cells[Point{X: turnX, Y: returnY}] = '<'
	result.Cells[Point{X: 0, Y: returnY}] = '^'
	if err := overlay(&result, body, bodyX, 0); err != nil {
		return box{}, err
	}
	return result, nil
}

func overlay(destination *box, source box, xOffset, yOffset int) error {
	for point, value := range source.Cells {
		target := Point{X: point.X + xOffset, Y: point.Y + yOffset}
		if existing, ok := destination.Cells[target]; ok && existing != value {
			return fmt.Errorf("layout conflict at (%d,%d): %q versus %q", target.X, target.Y, existing, value)
		}
		destination.Cells[target] = value
	}
	for _, ref := range source.Refs {
		ref.X += xOffset
		ref.Y += yOffset
		destination.Refs = append(destination.Refs, ref)
	}
	return nil
}

type portCandidate struct {
	Side   string
	Offset int
	Point  Point
	Score  int
}

func assignAutoPorts(ports []Port, room box) error {
	used := make(map[string]bool)
	for index := range ports {
		if ports[index].Side != "auto" {
			used[ports[index].Side+":"+strconv.Itoa(ports[index].Offset)] = true
		}
	}
	for _, direction := range []string{"input", "output"} {
		if err := assignPortGroup(ports, room, direction, used); err != nil {
			return err
		}
	}
	return nil
}

func assignPortGroup(ports []Port, room box, direction string, globallyUsed map[string]bool) error {
	var indices []int
	for index := range ports {
		if ports[index].Direction == direction && ports[index].Side == "auto" {
			indices = append(indices, index)
		}
	}
	if len(indices) == 0 {
		return nil
	}
	if assignWildcardPortGroup(ports, room, direction, indices, globallyUsed) {
		return nil
	}

	candidateSets := make(map[int][]portCandidate)
	for _, index := range indices {
		var refs []operationRef
		for _, ref := range room.Refs {
			wildcard := ref.Port == "*" &&
				((direction == "input" && ref.Kind == "input_any") ||
					(direction == "output" && ref.Kind == "broadcast"))
			if ref.Port == ports[index].Name || wildcard {
				refs = append(refs, ref)
			}
		}
		if len(refs) == 0 {
			return fmt.Errorf("port %q is never used", ports[index].Name)
		}
		for offset := 0; offset < room.Width; offset++ {
			candidateSets[index] = append(candidateSets[index],
				scoreCandidate("top", offset, Point{X: offset, Y: -1}, refs),
				scoreCandidate("bottom", offset, Point{X: offset, Y: room.Height}, refs),
			)
		}
		for offset := 0; offset < room.Height; offset++ {
			candidateSets[index] = append(candidateSets[index],
				scoreCandidate("left", offset, Point{X: -1, Y: offset}, refs),
				scoreCandidate("right", offset, Point{X: room.Width, Y: offset}, refs),
			)
		}
		sort.Slice(candidateSets[index], func(left, right int) bool {
			leftCandidate := candidateSets[index][left]
			rightCandidate := candidateSets[index][right]
			if leftCandidate.Score != rightCandidate.Score {
				return leftCandidate.Score < rightCandidate.Score
			}
			if leftCandidate.Point.Y != rightCandidate.Point.Y {
				return leftCandidate.Point.Y < rightCandidate.Point.Y
			}
			return leftCandidate.Point.X < rightCandidate.Point.X
		})
	}

	if coordinatePortAssignments(
		ports,
		room,
		direction,
		indices,
		candidateSets,
		globallyUsed,
	) {
		for _, index := range indices {
			globallyUsed[ports[index].Side+":"+strconv.Itoa(ports[index].Offset)] = true
		}
		return nil
	}

	limits := []int{8, 16, 32, 64, 128, 256}
	for _, limit := range limits {
		used := make(map[string]bool, len(globallyUsed)+len(indices))
		for key, value := range globallyUsed {
			used[key] = value
		}
		if searchPortAssignments(ports, room, direction, indices, candidateSets, used, 0, limit) {
			for _, index := range indices {
				globallyUsed[ports[index].Side+":"+strconv.Itoa(ports[index].Offset)] = true
			}
			return nil
		}
	}
	names := make([]string, len(indices))
	for index, portIndex := range indices {
		names[index] = ports[portIndex].Name
	}
	return fmt.Errorf("could not place %s ports %s without incorrect nearest-pipe bindings", direction, strings.Join(names, ", "))
}

func assignWildcardPortGroup(
	ports []Port,
	room box,
	direction string,
	indices []int,
	globallyUsed map[string]bool,
) bool {
	hasWildcard := false
	for _, ref := range room.Refs {
		refDirection := "output"
		if ref.Kind == "input" || ref.Kind == "input_any" {
			refDirection = "input"
		}
		if refDirection != direction {
			continue
		}
		if ref.Port != "*" {
			return false
		}
		hasWildcard = true
	}
	if !hasWildcard {
		return false
	}

	var candidates []portCandidate
	sides := []struct {
		name   string
		length int
	}{
		{"top", room.Width},
		{"right", room.Height},
		{"bottom", room.Width},
		{"left", room.Height},
	}
	maxLength := max(room.Width, room.Height)
	for step := 0; step < maxLength; step++ {
		for _, side := range sides {
			if step >= side.length {
				continue
			}
			offset := (side.length/2 + step*(side.length/2+1)) % side.length
			candidates = append(candidates, portCandidate{Side: side.name, Offset: offset})
		}
	}

	used := make(map[string]bool, len(globallyUsed)+len(indices))
	for key, value := range globallyUsed {
		used[key] = value
	}
	for position, index := range indices {
		assigned := false
		for attempt := 0; attempt < len(candidates); attempt++ {
			candidate := candidates[(position+attempt)%len(candidates)]
			key := candidate.Side + ":" + strconv.Itoa(candidate.Offset)
			if used[key] {
				continue
			}
			ports[index].Side = candidate.Side
			ports[index].Offset = candidate.Offset
			used[key] = true
			globallyUsed[key] = true
			assigned = true
			break
		}
		if !assigned {
			return false
		}
	}
	return true
}

func coordinatePortAssignments(
	ports []Port,
	room box,
	direction string,
	indices []int,
	candidateSets map[int][]portCandidate,
	globallyUsed map[string]bool,
) bool {
	for restart := 0; restart < 16; restart++ {
		used := make(map[string]bool, len(globallyUsed)+len(indices))
		for key, value := range globallyUsed {
			used[key] = value
		}
		valid := true
		for depth, index := range indices {
			candidates := candidateSets[index]
			start := (restart + depth) % len(candidates)
			assigned := false
			for offset := 0; offset < len(candidates); offset++ {
				candidate := candidates[(start+offset)%len(candidates)]
				key := candidate.Side + ":" + strconv.Itoa(candidate.Offset)
				if used[key] {
					continue
				}
				ports[index].Side = candidate.Side
				ports[index].Offset = candidate.Offset
				used[key] = true
				assigned = true
				break
			}
			if !assigned {
				valid = false
				break
			}
		}
		if !valid {
			continue
		}

		for pass := 0; pass < 32; pass++ {
			changed := false
			for _, index := range indices {
				oldKey := ports[index].Side + ":" + strconv.Itoa(ports[index].Offset)
				delete(used, oldKey)
				best := portCandidate{
					Side:   ports[index].Side,
					Offset: ports[index].Offset,
				}
				bestScore := portAssignmentScore(ports, room, direction)
				for _, candidate := range candidateSets[index] {
					key := candidate.Side + ":" + strconv.Itoa(candidate.Offset)
					if used[key] {
						continue
					}
					ports[index].Side = candidate.Side
					ports[index].Offset = candidate.Offset
					score := portAssignmentScore(ports, room, direction)
					if score < bestScore {
						best = candidate
						bestScore = score
					}
				}
				if ports[index].Side != best.Side || ports[index].Offset != best.Offset {
					changed = true
				}
				ports[index].Side = best.Side
				ports[index].Offset = best.Offset
				used[best.Side+":"+strconv.Itoa(best.Offset)] = true
			}
			if directionBindingsMatch(ports, room, direction) {
				return true
			}
			if !changed {
				break
			}
		}
		for _, index := range indices {
			ports[index].Side = "auto"
			ports[index].Offset = -1
		}
	}
	return false
}

func portAssignmentScore(ports []Port, room box, direction string) int64 {
	var candidates []Port
	for _, port := range ports {
		if port.Direction == direction {
			if port.Side == "auto" {
				return 1 << 62
			}
			candidates = append(candidates, port)
		}
	}
	var mismatches, totalDistance int64
	for _, ref := range room.Refs {
		refDirection := "output"
		if ref.Kind == "input" || ref.Kind == "input_any" {
			refDirection = "input"
		}
		if refDirection != direction || ref.Kind == "broadcast" || ref.Kind == "input_any" {
			continue
		}
		selected := nearestPort(candidates, ref.Point, room)
		if selected.Name != ref.Port {
			mismatches++
		}
		for _, candidate := range candidates {
			if candidate.Name == ref.Port {
				totalDistance += int64(distance(ref.Point, attachmentPoint(candidate, room)))
				break
			}
		}
	}
	return mismatches*1_000_000_000 + totalDistance
}

func searchPortAssignments(
	ports []Port,
	room box,
	direction string,
	indices []int,
	candidateSets map[int][]portCandidate,
	used map[string]bool,
	depth int,
	limit int,
) bool {
	if depth == len(indices) {
		return directionBindingsMatch(ports, room, direction)
	}
	index := indices[depth]
	candidates := candidateSets[index]
	if len(candidates) > limit {
		candidates = candidates[:limit]
	}
	for _, candidate := range candidates {
		key := candidate.Side + ":" + strconv.Itoa(candidate.Offset)
		if used[key] {
			continue
		}
		ports[index].Side = candidate.Side
		ports[index].Offset = candidate.Offset
		used[key] = true
		if searchPortAssignments(ports, room, direction, indices, candidateSets, used, depth+1, limit) {
			return true
		}
		delete(used, key)
		ports[index].Side = "auto"
		ports[index].Offset = -1
	}
	return false
}

func directionBindingsMatch(ports []Port, room box, direction string) bool {
	var candidates []Port
	for _, port := range ports {
		if port.Direction == direction {
			if port.Side == "auto" {
				return false
			}
			candidates = append(candidates, port)
		}
	}
	for _, ref := range room.Refs {
		refDirection := "output"
		if ref.Kind == "input" || ref.Kind == "input_any" {
			refDirection = "input"
		}
		if refDirection != direction || ref.Kind == "broadcast" || ref.Kind == "input_any" {
			continue
		}
		if nearestPort(candidates, ref.Point, room).Name != ref.Port {
			return false
		}
	}
	return true
}

func scoreCandidate(side string, offset int, point Point, refs []operationRef) portCandidate {
	score := 0
	for _, ref := range refs {
		score += distance(point, ref.Point)
	}
	return portCandidate{Side: side, Offset: offset, Point: point, Score: score}
}

func validatePorts(ports []Port, room box) error {
	byName := make(map[string]Port)
	attachments := make(map[string]string)
	var inputs, outputs []Port
	for _, port := range ports {
		if (port.Side == "top" || port.Side == "bottom") && port.Offset >= room.Width {
			return fmt.Errorf("port %q offset %d is outside width %d", port.Name, port.Offset, room.Width)
		}
		if (port.Side == "left" || port.Side == "right") && port.Offset >= room.Height {
			return fmt.Errorf("port %q offset %d is outside height %d", port.Name, port.Offset, room.Height)
		}
		attachment := port.Side + ":" + strconv.Itoa(port.Offset)
		if existing, exists := attachments[attachment]; exists {
			return fmt.Errorf("ports %q and %q use the same attachment", existing, port.Name)
		}
		attachments[attachment] = port.Name
		byName[port.Name] = port
		if port.Direction == "input" {
			inputs = append(inputs, port)
		} else {
			outputs = append(outputs, port)
		}
	}
	for _, ref := range room.Refs {
		if ref.Port == "*" {
			if ref.Kind == "broadcast" && len(outputs) == 0 {
				return fmt.Errorf("line %d: broadcast requires an output port", ref.Line)
			}
			if ref.Kind == "input_any" && len(inputs) == 0 {
				return fmt.Errorf("line %d: recv any requires an input port", ref.Line)
			}
			continue
		}
		port, exists := byName[ref.Port]
		if !exists {
			return fmt.Errorf("line %d: unknown port %q", ref.Line, ref.Port)
		}
		if ref.Kind == "input" && port.Direction != "input" {
			return fmt.Errorf("line %d: recv requires an input port, got %q", ref.Line, ref.Port)
		}
		if (ref.Kind == "output" || ref.Kind == "broadcast") && port.Direction != "output" {
			return fmt.Errorf("line %d: send requires an output port, got %q", ref.Line, ref.Port)
		}
		if ref.Kind == "broadcast" {
			continue
		}
		candidates := inputs
		if ref.Kind == "output" {
			candidates = outputs
		}
		selected := nearestPort(candidates, ref.Point, room)
		if selected.Name != ref.Port {
			return fmt.Errorf(
				"line %d: %s %q at (%d,%d) binds to nearer port %q",
				ref.Line, ref.Kind, ref.Port, ref.X, ref.Y, selected.Name,
			)
		}
	}
	return nil
}

func nearestPort(ports []Port, operation Point, room box) Port {
	if len(ports) == 0 {
		return Port{}
	}
	best := ports[0]
	bestPoint := attachmentPoint(best, room)
	for _, candidate := range ports[1:] {
		point := attachmentPoint(candidate, room)
		bestDistance := distance(operation, bestPoint)
		candidateDistance := distance(operation, point)
		if candidateDistance < bestDistance ||
			(candidateDistance == bestDistance && (point.Y < bestPoint.Y || (point.Y == bestPoint.Y && point.X < bestPoint.X))) {
			best = candidate
			bestPoint = point
		}
	}
	return best
}

func attachmentPoint(port Port, room box) Point {
	switch port.Side {
	case "top":
		return Point{X: port.Offset, Y: -1}
	case "bottom":
		return Point{X: port.Offset, Y: room.Height}
	case "left":
		return Point{X: -1, Y: port.Offset}
	default:
		return Point{X: room.Width, Y: port.Offset}
	}
}

func distance(left, right Point) int {
	return abs(left.X-right.X) + abs(left.Y-right.Y)
}

func abs(value int) int {
	if value < 0 {
		return -value
	}
	return value
}

func renderDebug(room box) string {
	rows := make([]string, room.Height)
	for y := 0; y < room.Height; y++ {
		row := make([]byte, room.Width)
		for x := range row {
			row[x] = ' '
		}
		for x := 0; x < room.Width; x++ {
			if value, ok := room.Cells[Point{X: x, Y: y}]; ok {
				row[x] = value
			}
		}
		rows[y] = string(row)
	}
	return strings.Join(rows, "\n")
}
