package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
)

type compiledBlock struct {
	Name            string
	File            string
	Width           int
	Height          int
	BacktickOffsets []int
	Ports           map[string]generatedPort
}

type blockFile struct {
	Size     string                   `json:"size"`
	Interior []string                 `json:"interior"`
	Ports    map[string]generatedPort `json:"ports"`
}

type generatedPort struct {
	Type        string `json:"type"`
	Side        string `json:"side"`
	OffsetRange []int  `json:"offset_range"`
	LengthRange []int  `json:"length_range"`
}

type generatedBlock struct {
	Name     string                   `json:"name"`
	Size     string                   `json:"size"`
	Interior []string                 `json:"interior"`
	Ports    map[string]generatedPort `json:"ports"`
}

type floorBlock struct {
	ID   string `json:"id"`
	File string `json:"file,omitempty"`
	Type string `json:"type,omitempty"`
	X    int    `json:"x"`
	Y    int    `json:"y"`
}

type floorConnection struct {
	Src       string       `json:"src"`
	Dst       string       `json:"dst"`
	SrcSide   string       `json:"src_side,omitempty"`
	DstSide   string       `json:"dst_side,omitempty"`
	SrcOffset *int         `json:"src_offset,omitempty"`
	DstOffset *int         `json:"dst_offset,omitempty"`
	Waypoints []floorPoint `json:"waypoints,omitempty"`
}

type floorPoint struct {
	X int `json:"x"`
	Y int `json:"y"`
}

type floorDescription struct {
	GridWidth   int               `json:"grid_width"`
	GridHeight  int               `json:"grid_height"`
	Blocks      []floorBlock      `json:"blocks"`
	Connections []floorConnection `json:"connections"`
}

type directedEdge struct {
	Source      string
	Destination string
	MinSize     int
	MaxSize     int
}

func compileMan(program *Program, outputPath, floorplanMode string) error {
	lowered, edges, err := lowerNamedPipes(program)
	if err != nil {
		return err
	}
	repositoryRoot, err := findRepositoryRoot()
	if err != nil {
		return err
	}
	simRoot := filepath.Join(repositoryRoot, "sim")
	blangRoot := filepath.Join(repositoryRoot, "blang")
	tempDir, err := os.MkdirTemp("", "plumber-man-*")
	if err != nil {
		return err
	}
	if os.Getenv("PLUMBER_KEEP_TEMP") == "" {
		defer os.RemoveAll(tempDir)
	} else {
		fmt.Fprintf(os.Stderr, "Plumber work directory: %s\n", tempDir)
	}

	blocks := make([]compiledBlock, 0, len(lowered.Blocks))
	for _, actor := range lowered.Blocks {
		blockPath := filepath.Join(tempDir, actor.Name+".block")
		if isPipeRelay(actor) {
			if writeErr := writePipeRelay(actor, edges, blockPath); writeErr != nil {
				return writeErr
			}
		} else {
			source, translateErr := renderBlang(actor, edges)
			if translateErr != nil {
				return translateErr
			}
			sourcePath := filepath.Join(tempDir, actor.Name+".bl")
			if writeErr := os.WriteFile(sourcePath, []byte(source), 0644); writeErr != nil {
				return writeErr
			}
			if runErr := runGoTool(
				blangRoot,
				".",
				"-input", sourcePath,
				"-output", blockPath,
			); runErr != nil {
				return fmt.Errorf("compile block %s: %w", actor.Name, runErr)
			}
		}

		data, readErr := os.ReadFile(blockPath)
		if readErr != nil {
			return readErr
		}
		var definition blockFile
		if unmarshalErr := json.Unmarshal(data, &definition); unmarshalErr != nil {
			return unmarshalErr
		}
		width, height, sizeErr := parseSize(definition.Size)
		if sizeErr != nil {
			return fmt.Errorf("block %s: %w", actor.Name, sizeErr)
		}
		blocks = append(blocks, compiledBlock{
			Name:            actor.Name,
			File:            blockPath,
			Width:           width,
			Height:          height,
			BacktickOffsets: backtickOffsets(definition.Interior),
			Ports:           definition.Ports,
		})
	}

	var code []byte
	var side int
	switch floorplanMode {
	case "shelf":
		code, side, err = searchFloorplan(simRoot, tempDir, blocks, edges, 100)
	case "anneal":
		code, side, err = searchAnnealedFloorplan(
			simRoot,
			tempDir,
			blocks,
			edges,
			100,
		)
	default:
		return fmt.Errorf(
			"unknown floorplanning mode %q; expected shelf or anneal",
			floorplanMode,
		)
	}
	if err != nil {
		return err
	}
	fmt.Fprintf(os.Stderr, "Plumber floorplan side: %d\n", side)
	return os.WriteFile(outputPath, code, 0644)
}

func searchFloorplan(
	simRoot string,
	tempDir string,
	blocks []compiledBlock,
	edges []directedEdge,
	startSide int,
) ([]byte, int, error) {
	var best []byte
	bestSide := 0
	minSide := 1
	for _, block := range blocks {
		if block.Width+2 > minSide {
			minSide = block.Width + 2
		}
		if block.Height+2 > minSide {
			minSide = block.Height + 2
		}
	}
	for side := startSide; side >= minSide; side-- {
		layouts := []struct {
			margin int
			gap    int
		}{
			{8, 8},
			{6, 8},
			{4, 8},
			{6, 6},
			{4, 6},
			{4, 4},
			{4, 2},
		}
		foundAtSide := false
		for layoutIndex, layout := range layouts {
			for outputVariant := 0; outputVariant < 4; outputVariant++ {
				floor, fits := buildFloor(
					blocks,
					edges,
					side,
					layout.margin,
					layout.gap,
					outputVariant,
				)
				if !fits {
					continue
				}
				floorData, err := json.MarshalIndent(floor, "", "  ")
				if err != nil {
					return nil, 0, err
				}
				base := fmt.Sprintf(
					"program-%d-%d-%d",
					side,
					layoutIndex,
					outputVariant,
				)
				floorPath := filepath.Join(tempDir, base+".floor")
				manPath := filepath.Join(tempDir, base+".man")
				if err := os.WriteFile(floorPath, floorData, 0644); err != nil {
					return nil, 0, err
				}
				if err := runGoFile(
					simRoot,
					"floorplan.go",
					"-layout", floorPath,
					"-output", manPath,
				); err != nil {
					continue
				}
				if err := validateGeneratedMan(simRoot, manPath); err != nil {
					continue
				}
				code, err := os.ReadFile(manPath)
				if err != nil {
					return nil, 0, err
				}
				width, height := manDimensions(code)
				if width > side || height > side {
					continue
				}
				best = code
				bestSide = max(width, height)
				foundAtSide = true
				break
			}
			if foundAtSide {
				break
			}
		}
	}
	if best == nil {
		return nil, 0, fmt.Errorf(
			"floorplan: no valid placement fits a %dx%d grid",
			startSide,
			startSide,
		)
	}
	return best, bestSide, nil
}

func manDimensions(code []byte) (int, int) {
	lines := strings.Split(strings.TrimRight(string(code), "\n"), "\n")
	width := 0
	for _, line := range lines {
		if len(line) > width {
			width = len(line)
		}
	}
	return width, len(lines)
}

func backtickOffsets(interior []string) []int {
	seen := make(map[int]bool)
	for _, row := range interior {
		for offset := 0; offset < len(row); offset++ {
			if row[offset] == '`' {
				seen[offset] = true
			}
		}
	}
	offsets := make([]int, 0, len(seen))
	for offset := range seen {
		offsets = append(offsets, offset)
	}
	sort.Ints(offsets)
	return offsets
}

func isPipeRelay(actor *Block) bool {
	if !strings.HasPrefix(actor.Name, "__pipe_") || len(actor.Body) != 2 {
		return false
	}
	receive, receiveOK := actor.Body[0].(Instruction)
	send, sendOK := actor.Body[1].(Instruction)
	return receiveOK && sendOK &&
		receive.Kind == InstructionReceive &&
		send.Kind == InstructionSend
}

func writePipeRelay(actor *Block, edges []directedEdge, path string) error {
	receive := actor.Body[0].(Instruction)
	send := actor.Body[1].(Instruction)
	inMin, inMax := edgeRange(edges, receive.Peer, actor.Name)
	outMin, outMax := edgeRange(edges, actor.Name, send.Peer)
	definition := generatedBlock{
		Name:     actor.Name,
		Size:     "3x2",
		Interior: []string{">@v", "^sU"},
		Ports: map[string]generatedPort{
			inputPort(receive.Peer): {
				Type:        "input",
				Side:        "right",
				OffsetRange: []int{1, 1},
				LengthRange: []int{inMin, inMax},
			},
			outputPort(send.Peer): {
				Type:        "output",
				Side:        "left",
				OffsetRange: []int{1, 1},
				LengthRange: []int{outMin, outMax},
			},
		},
	}
	data, err := json.MarshalIndent(definition, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

func renderBlang(actor *Block, edges []directedEdge) (string, error) {
	inputs := make(map[string]bool)
	outputs := make(map[string]bool)
	collectEndpoints(actor.Body, inputs, outputs)

	var result strings.Builder
	fmt.Fprintf(&result, "block %s\n\n", actor.Name)
	inputNames := sortedKeys(inputs)
	outputNames := sortedKeys(outputs)
	for _, endpoint := range inputNames {
		minSize, maxSize := edgeRange(edges, endpoint, actor.Name)
		fmt.Fprintf(
			&result,
			"input %s auto %d %d\n",
			inputPort(endpoint),
			minSize,
			maxSize,
		)
	}
	for _, endpoint := range outputNames {
		minSize, maxSize := edgeRange(edges, actor.Name, endpoint)
		fmt.Fprintf(
			&result,
			"output %s auto %d %d\n",
			outputPort(endpoint),
			minSize,
			maxSize,
		)
	}
	result.WriteString("\nforever {\n")
	renderStatements(&result, actor.Body, 1)
	result.WriteString("}\n")
	return result.String(), nil
}

func edgeRange(edges []directedEdge, source, destination string) (int, int) {
	for _, edge := range edges {
		if edge.Source == source && edge.Destination == destination {
			if edge.MaxSize > 0 {
				return edge.MinSize, edge.MaxSize
			}
			return 2, 1_000_000
		}
	}
	return 2, 1_000_000
}

func lowerNamedPipes(program *Program) (*Program, []directedEdge, error) {
	pipeByName := make(map[string]*Pipe)
	for _, pipe := range program.Pipes {
		pipeByName[pipe.Name] = pipe
	}

	producers := make(map[string]map[string]bool)
	consumers := make(map[string]map[string]bool)
	for _, actor := range program.Blocks {
		collectPipeUsers(actor.Name, actor.Body, pipeByName, producers, consumers)
	}

	aliases := make(map[string]string)
	var relays []*Block
	var pipeEdges []directedEdge
	for _, pipe := range program.Pipes {
		producerNames := sortedKeys(producers[pipe.Name])
		consumerNames := sortedKeys(consumers[pipe.Name])
		if len(producerNames) != 1 || len(consumerNames) != 1 {
			return nil, nil, fmt.Errorf(
				"pipe %s must have exactly one sending block and one receiving block; got %d and %d",
				pipe.Name,
				len(producerNames),
				len(consumerNames),
			)
		}
		producer := producerNames[0]
		consumer := consumerNames[0]
		relay := "__pipe_" + pipe.Name
		aliases[pipe.Name] = relay
		relays = append(relays, &Block{
			Name: relay,
			Line: pipe.Line,
			Body: []Stmt{
				Instruction{Kind: InstructionReceive, Peer: producer, Line: pipe.Line},
				Instruction{Kind: InstructionSend, Peer: consumer, Line: pipe.Line},
			},
		})
		pipeEdges = append(pipeEdges,
			directedEdge{Source: producer, Destination: relay, MinSize: 2},
			directedEdge{
				Source:      relay,
				Destination: consumer,
				MinSize:     pipe.MinSize,
				MaxSize:     pipe.MaxSize,
			},
		)
	}

	lowered := &Program{Name: program.Name}
	for _, actor := range program.Blocks {
		lowered.Blocks = append(lowered.Blocks, &Block{
			Name: actor.Name,
			Line: actor.Line,
			Body: replaceEndpoints(actor.Body, aliases),
		})
		for _, relay := range relays {
			receive := relay.Body[0].(Instruction)
			if receive.Peer == actor.Name {
				lowered.Blocks = append(lowered.Blocks, relay)
			}
		}
	}

	edges, err := validateChannels(lowered)
	if err != nil {
		return nil, nil, err
	}
	for index := range edges {
		for _, pipeEdge := range pipeEdges {
			if edges[index].Source == pipeEdge.Source &&
				edges[index].Destination == pipeEdge.Destination {
				edges[index].MinSize = pipeEdge.MinSize
				edges[index].MaxSize = pipeEdge.MaxSize
			}
		}
	}
	return lowered, edges, nil
}

func collectPipeUsers(
	actor string,
	statements []Stmt,
	pipes map[string]*Pipe,
	producers map[string]map[string]bool,
	consumers map[string]map[string]bool,
) {
	for _, statement := range statements {
		switch value := statement.(type) {
		case Instruction:
			var users map[string]map[string]bool
			if value.Kind == InstructionSend {
				users = producers
			} else if value.Kind == InstructionReceive {
				users = consumers
			}
			if users != nil && pipes[value.Peer] != nil {
				if users[value.Peer] == nil {
					users[value.Peer] = make(map[string]bool)
				}
				users[value.Peer][actor] = true
			}
		case Repeat:
			collectPipeUsers(actor, value.Body, pipes, producers, consumers)
		case WhilePositive:
			collectPipeUsers(actor, value.Body, pipes, producers, consumers)
		case SignBranch:
			collectPipeUsers(actor, value.Negative, pipes, producers, consumers)
			collectPipeUsers(actor, value.Zero, pipes, producers, consumers)
			collectPipeUsers(actor, value.Positive, pipes, producers, consumers)
		}
	}
}

func replaceEndpoints(statements []Stmt, aliases map[string]string) []Stmt {
	result := make([]Stmt, 0, len(statements))
	for _, statement := range statements {
		switch value := statement.(type) {
		case Instruction:
			if alias := aliases[value.Peer]; alias != "" {
				value.Peer = alias
			}
			result = append(result, value)
		case Repeat:
			value.Body = replaceEndpoints(value.Body, aliases)
			result = append(result, value)
		case WhilePositive:
			value.Body = replaceEndpoints(value.Body, aliases)
			result = append(result, value)
		case SignBranch:
			value.Negative = replaceEndpoints(value.Negative, aliases)
			value.Zero = replaceEndpoints(value.Zero, aliases)
			value.Positive = replaceEndpoints(value.Positive, aliases)
			result = append(result, value)
		}
	}
	return result
}

func collectEndpoints(
	statements []Stmt,
	inputs map[string]bool,
	outputs map[string]bool,
) {
	for _, statement := range statements {
		switch value := statement.(type) {
		case Instruction:
			if value.Kind == InstructionReceive {
				inputs[value.Peer] = true
			}
			if value.Kind == InstructionSend {
				outputs[value.Peer] = true
			}
		case Repeat:
			collectEndpoints(value.Body, inputs, outputs)
		case WhilePositive:
			collectEndpoints(value.Body, inputs, outputs)
		case SignBranch:
			collectEndpoints(value.Negative, inputs, outputs)
			collectEndpoints(value.Zero, inputs, outputs)
			collectEndpoints(value.Positive, inputs, outputs)
		}
	}
}

func renderStatements(result *strings.Builder, statements []Stmt, depth int) {
	indent := strings.Repeat("  ", depth)
	for _, statement := range statements {
		switch value := statement.(type) {
		case Instruction:
			result.WriteString(indent)
			result.WriteString(renderInstruction(value))
			result.WriteByte('\n')
		case Repeat:
			fmt.Fprintf(result, "%srepeat A {\n", indent)
			renderStatements(result, value.Body, depth+1)
			fmt.Fprintf(result, "%s}\n", indent)
		case WhilePositive:
			fmt.Fprintf(result, "%swhile positive A {\n", indent)
			renderStatements(result, value.Body, depth+1)
			fmt.Fprintf(result, "%s}\n", indent)
		case SignBranch:
			fmt.Fprintf(result, "%sif sign A {\n", indent)
			for _, branch := range []struct {
				name string
				body []Stmt
			}{
				{"negative", value.Negative},
				{"zero", value.Zero},
				{"positive", value.Positive},
			} {
				fmt.Fprintf(result, "%s  %s {\n", indent, branch.name)
				renderStatements(result, branch.body, depth+2)
				fmt.Fprintf(result, "%s  }\n", indent)
			}
			fmt.Fprintf(result, "%s}\n", indent)
		}
	}
}

func renderInstruction(instruction Instruction) string {
	switch instruction.Kind {
	case InstructionLoad:
		return "A = " + strconv.FormatInt(instruction.Value, 10)
	case InstructionCopy:
		return "B = A"
	case InstructionSwap:
		return "swap"
	case InstructionAdd:
		return "A += B"
	case InstructionSubtract:
		return "A -= B"
	case InstructionMultiply:
		return "A *= B"
	case InstructionModulo:
		return "A %= B"
	case InstructionDivide:
		return "A /= B"
	case InstructionNegate:
		return "A = -A"
	case InstructionAnd:
		return "A &= B"
	case InstructionOr:
		return "A |= B"
	case InstructionXor:
		return "A ^= B"
	case InstructionShiftLeft:
		return "A <<= B"
	case InstructionShiftRight:
		return "A >>= B"
	case InstructionReceive:
		return "A = recv " + inputPort(instruction.Peer)
	case InstructionSend:
		return "send " + outputPort(instruction.Peer)
	case InstructionHalt:
		return "halt"
	case InstructionNop:
		return "nop"
	default:
		panic("unsupported Plumber instruction " + instruction.Kind)
	}
}

func validateChannels(program *Program) ([]directedEdge, error) {
	sends := make(map[directedEdge]bool)
	receives := make(map[directedEdge]bool)
	for _, actor := range program.Blocks {
		collectChannels(actor.Name, actor.Body, sends, receives)
	}

	for edge := range sends {
		if edge.Destination == "output" {
			continue
		}
		if edge.Source == edge.Destination {
			return nil, fmt.Errorf(
				"block %s uses a self-channel; Little Man pipes cannot connect a room to itself",
				edge.Source,
			)
		}
		if !receives[edge] {
			return nil, fmt.Errorf(
				"block %s sends to %s, but %s never receives from %s",
				edge.Source,
				edge.Destination,
				edge.Destination,
				edge.Source,
			)
		}
	}
	for edge := range receives {
		if edge.Source == "input" {
			continue
		}
		if !sends[edge] {
			return nil, fmt.Errorf(
				"block %s receives from %s, but %s never sends to %s",
				edge.Destination,
				edge.Source,
				edge.Source,
				edge.Destination,
			)
		}
	}

	edges := make([]directedEdge, 0, len(sends)+1)
	for edge := range receives {
		if edge.Source == "input" {
			edges = append(edges, edge)
		}
	}
	for edge := range sends {
		edges = append(edges, edge)
	}
	blockOrder := make(map[string]int)
	for index, block := range program.Blocks {
		blockOrder[block.Name] = index
	}
	sort.Slice(edges, func(left, right int) bool {
		leftRelay := strings.HasPrefix(edges[left].Source, "__pipe_")
		rightRelay := strings.HasPrefix(edges[right].Source, "__pipe_")
		if leftRelay != rightRelay {
			return !leftRelay
		}
		if blockOrder[edges[left].Source] != blockOrder[edges[right].Source] {
			return blockOrder[edges[left].Source] < blockOrder[edges[right].Source]
		}
		leftDestinationRelay := strings.HasPrefix(edges[left].Destination, "__pipe_")
		rightDestinationRelay := strings.HasPrefix(edges[right].Destination, "__pipe_")
		if leftDestinationRelay != rightDestinationRelay {
			return !leftDestinationRelay
		}
		if edges[left].Source != edges[right].Source {
			return edges[left].Source < edges[right].Source
		}
		return edges[left].Destination < edges[right].Destination
	})
	return edges, nil
}

func collectChannels(
	actor string,
	statements []Stmt,
	sends map[directedEdge]bool,
	receives map[directedEdge]bool,
) {
	for _, statement := range statements {
		switch value := statement.(type) {
		case Instruction:
			if value.Kind == InstructionSend {
				sends[directedEdge{Source: actor, Destination: value.Peer}] = true
			}
			if value.Kind == InstructionReceive {
				receives[directedEdge{Source: value.Peer, Destination: actor}] = true
			}
		case Repeat:
			collectChannels(actor, value.Body, sends, receives)
		case WhilePositive:
			collectChannels(actor, value.Body, sends, receives)
		case SignBranch:
			collectChannels(actor, value.Negative, sends, receives)
			collectChannels(actor, value.Zero, sends, receives)
			collectChannels(actor, value.Positive, sends, receives)
		}
	}
}

func buildFloor(
	blocks []compiledBlock,
	edges []directedEdge,
	targetSide int,
	margin int,
	gap int,
	outputVariant int,
) (floorDescription, bool) {
	const (
		roomPadding = 2
	)

	maxHeight := 3
	maxBottom := margin + 3
	maxRight := margin
	shelfWidth := 0
	widestBlock := ""
	for _, block := range blocks {
		if block.Width+roomPadding > shelfWidth {
			shelfWidth = block.Width + roomPadding
			widestBlock = block.Name
		}
	}
	nextX, nextY, rowHeight := margin, margin, 0
	usedBacktickColumns := make(map[int]bool)
	for _, block := range blocks {
		if block.Name == widestBlock {
			for _, offset := range block.BacktickOffsets {
				usedBacktickColumns[margin+1+offset] = true
			}
			break
		}
	}
	var floorBlocks []floorBlock

	input := floorBlock{
		ID:   "input",
		Type: "I",
		X:    max(0, margin-3),
		Y:    margin,
	}
	floorBlocks = append(floorBlocks, input)
	for _, block := range blocks {
		if nextX > margin &&
			nextX+block.Width+roomPadding > margin+shelfWidth {
			nextX = margin
			nextY += rowHeight + gap
			rowHeight = 0
		}
		if block.Name != widestBlock {
			for {
				conflict := false
				for _, offset := range block.BacktickOffsets {
					if usedBacktickColumns[nextX+1+offset] {
						conflict = true
						break
					}
				}
				if !conflict {
					break
				}
				nextX++
			}
		}
		placement := floorBlock{
			ID:   block.Name,
			File: block.File,
			X:    nextX,
			Y:    nextY,
		}
		floorBlocks = append(floorBlocks, placement)
		for _, offset := range block.BacktickOffsets {
			usedBacktickColumns[placement.X+1+offset] = true
		}
		nextX += block.Width + roomPadding + gap
		if block.Height+roomPadding > rowHeight {
			rowHeight = block.Height + roomPadding
		}
		right := placement.X + block.Width + roomPadding
		if right > maxRight {
			maxRight = right
		}
		if block.Height+roomPadding > maxHeight {
			maxHeight = block.Height + roomPadding
		}
		bottom := placement.Y + block.Height + roomPadding
		if bottom > maxBottom {
			maxBottom = bottom
		}
	}
	output := floorBlock{
		ID:   "output",
		Type: "O",
		X:    min(maxRight+gap, targetSide-4),
		Y:    maxBottom - 3,
	}
	switch outputVariant {
	case 1:
		output.X = margin
		output.Y = maxBottom + gap
	case 2:
		output.X = maxRight - 3
		output.Y = maxBottom + gap
	case 3:
		output.X = targetSide - 3
		output.Y = maxBottom + gap
	}
	floorBlocks = append(floorBlocks, output)

	var connections []floorConnection
	for _, category := range []string{"input", "output", "internal"} {
		for _, edge := range edges {
			isInput := edge.Source == "input"
			isOutput := edge.Destination == "output"
			switch category {
			case "internal":
				if isInput || isOutput {
					continue
				}
			case "input":
				if !isInput {
					continue
				}
			case "output":
				if !isOutput {
					continue
				}
			}

			switch {
			case isInput:
				connections = append(connections, floorConnection{
					Src: "input.out",
					Dst: edge.Destination + "." + inputPort("input"),
				})
			case isOutput:
				connections = append(connections, floorConnection{
					Src: edge.Source + "." + outputPort("output"),
					Dst: "output.in",
				})
			default:
				connections = append(connections, floorConnection{
					Src: edge.Source + "." + outputPort(edge.Destination),
					Dst: edge.Destination + "." + inputPort(edge.Source),
				})
			}
		}
	}

	type rectangle struct {
		x, y, width, height int
	}
	var occupied []rectangle
	for _, block := range floorBlocks {
		width, height := 3, 3
		if block.Type == "" {
			for _, compiled := range blocks {
				if compiled.Name == block.ID {
					width = compiled.Width + roomPadding
					height = compiled.Height + roomPadding
					break
				}
			}
		}
		if block.X < 0 || block.Y < 0 ||
			block.X+width > targetSide || block.Y+height > targetSide {
			return floorDescription{}, false
		}
		current := rectangle{block.X, block.Y, width, height}
		for _, other := range occupied {
			if current.x < other.x+other.width &&
				other.x < current.x+current.width &&
				current.y < other.y+other.height &&
				other.y < current.y+current.height {
				return floorDescription{}, false
			}
		}
		occupied = append(occupied, current)
	}

	return floorDescription{
		GridWidth:   targetSide,
		GridHeight:  targetSide,
		Blocks:      floorBlocks,
		Connections: connections,
	}, true
}

func inputPort(peer string) string {
	if peer == "input" {
		return "input"
	}
	return "from_" + peer
}

func outputPort(peer string) string {
	if peer == "output" {
		return "output"
	}
	return "to_" + peer
}

func sortedKeys(values map[string]bool) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func parseSize(raw string) (int, int, error) {
	left, right, ok := strings.Cut(raw, "x")
	if !ok {
		return 0, 0, fmt.Errorf("invalid block size %q", raw)
	}
	width, widthErr := strconv.Atoi(left)
	height, heightErr := strconv.Atoi(right)
	if widthErr != nil || heightErr != nil || width < 1 || height < 1 {
		return 0, 0, fmt.Errorf("invalid block size %q", raw)
	}
	return width, height, nil
}

func findRepositoryRoot() (string, error) {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		return "", fmt.Errorf("cannot locate repository root")
	}
	return filepath.Dir(filepath.Dir(file)), nil
}

func runGoTool(directory, packagePath string, args ...string) error {
	commandArgs := []string{"run", packagePath}
	commandArgs = append(commandArgs, args...)
	return runCommand(directory, "go", commandArgs...)
}

func runGoFile(directory, file string, args ...string) error {
	commandArgs := []string{"run", file}
	commandArgs = append(commandArgs, args...)
	return runCommand(directory, "go", commandArgs...)
}

func runCommand(directory, name string, args ...string) error {
	command := exec.Command(name, args...)
	command.Dir = directory
	command.Env = append(os.Environ(), "GOCACHE=/tmp/icfpc-go-cache")
	var output bytes.Buffer
	command.Stdout = &output
	command.Stderr = &output
	if err := command.Run(); err != nil {
		return fmt.Errorf("%s: %w\n%s", name, err, output.String())
	}
	return nil
}

func validateGeneratedMan(simRoot, path string) error {
	// benchmark.go parses before executing cases. A one-tick Sort run is enough
	// to validate the generated program without maintaining a separate fixture.
	tests := filepath.Join(filepath.Dir(simRoot), "public_tests", "sort.json")
	command := exec.Command(
		"go", "run",
		"benchmark.go", "parser.go", "simulator.go", "types.go", "literals.go",
		"-program", path,
		"-tests", tests,
		"-max-ticks", "1",
	)
	command.Dir = simRoot
	command.Env = append(os.Environ(), "GOCACHE=/tmp/icfpc-go-cache")
	var output bytes.Buffer
	command.Stdout = &output
	command.Stderr = &output
	err := command.Run()
	if err != nil && strings.Contains(output.String(), "parse program:") {
		return fmt.Errorf("generated .man is invalid: %s", strings.TrimSpace(output.String()))
	}
	// A one-tick benchmark failure is expected; successful parsing is enough.
	return nil
}
