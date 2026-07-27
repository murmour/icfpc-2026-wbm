package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"slices"
	"strings"
)

type state struct {
	a int
	b int
}

type transition struct {
	op   byte
	next func(state) state
}

func shortestBytePrograms(needed map[byte]bool) map[byte]string {
	best := make(map[byte]string)
	for value := byte(0); value <= 9; value++ {
		if needed[value] {
			best[value] = string('0' + value)
		}
	}

	const limit = 512
	var queue []state
	paths := make(map[state]string)
	for value := 0; value <= 9; value++ {
		current := state{a: value, b: value}
		paths[current] = string([]byte{byte('0' + value), 'M'})
		queue = append(queue, current)
	}

	transitions := []transition{
		{op: 'M', next: func(s state) state { return state{a: s.a, b: s.a} }},
		{op: 'W', next: func(s state) state { return state{a: s.b, b: s.a} }},
		{op: '+', next: func(s state) state { return state{a: s.a + s.b, b: s.b} }},
		{op: '-', next: func(s state) state { return state{a: s.a - s.b, b: s.b} }},
		{op: '*', next: func(s state) state { return state{a: s.a * s.b, b: s.b} }},
		{op: 'N', next: func(s state) state { return state{a: -s.a, b: s.b} }},
	}

	allFound := func() bool {
		for value := range needed {
			if _, ok := best[value]; !ok {
				return false
			}
		}
		return true
	}

	for head := 0; head < len(queue) && !allFound(); head++ {
		current := queue[head]
		path := paths[current]
		if current.a >= 0 && current.a <= 255 {
			value := byte(current.a)
			if needed[value] {
				if previous, ok := best[value]; !ok || len(path) < len(previous) {
					best[value] = path
				}
			}
		}

		for digit := 0; digit <= 9; digit++ {
			next := state{a: digit, b: current.b}
			if _, seen := paths[next]; seen {
				continue
			}
			paths[next] = path + string(byte('0'+digit))
			queue = append(queue, next)
		}
		for _, candidate := range transitions {
			next := candidate.next(current)
			if next.a < -limit || next.a > limit || next.b < -limit || next.b > limit {
				continue
			}
			if _, seen := paths[next]; seen {
				continue
			}
			paths[next] = path + string(candidate.op)
			queue = append(queue, next)
		}
	}

	if !allFound() {
		panic("could not synthesize every required byte")
	}
	return best
}

func chooseInteriorWidth(codeLength int) int {
	bestWidth := 0
	bestSide := int(^uint(0) >> 1)
	for interiorWidth := 20; interiorWidth <= 512; interiorWidth++ {
		firstCapacity := interiorWidth - 3
		rowCapacity := interiorWidth - 2
		rows := 1
		if codeLength > firstCapacity {
			rows += (codeLength - firstCapacity + rowCapacity - 1) / rowCapacity
		}

		mainWidth := interiorWidth + 2
		mainHeight := rows + 2
		totalWidth := mainWidth + 5
		side := max(totalWidth, mainHeight)
		if side < bestSide {
			bestWidth = interiorWidth
			bestSide = side
		}
	}
	return bestWidth
}

func splitRows(code string, interiorWidth int) []string {
	firstCapacity := interiorWidth - 3
	rowCapacity := interiorWidth - 2
	firstLength := min(firstCapacity, len(code))
	rows := []string{code[:firstLength]}
	code = code[firstLength:]
	for len(code) > 0 {
		length := min(rowCapacity, len(code))
		rows = append(rows, code[:length])
		code = code[length:]
	}
	return rows
}

func reverse(value string) string {
	bytes := []byte(value)
	slices.Reverse(bytes)
	return string(bytes)
}

func drawSolution(code string) string {
	interiorWidth := chooseInteriorWidth(len(code))
	rows := splitRows(code, interiorWidth)
	mainWidth := interiorWidth + 2
	mainHeight := len(rows) + 2
	totalWidth := mainWidth + 5
	grid := make([][]byte, mainHeight)
	for y := range grid {
		grid[y] = []byte(strings.Repeat(" ", totalWidth))
	}

	for x := 0; x < mainWidth; x++ {
		grid[0][x] = '-'
		grid[mainHeight-1][x] = '-'
	}
	for y := 0; y < mainHeight; y++ {
		grid[y][0] = '|'
		grid[y][mainWidth-1] = '|'
	}
	grid[0][0], grid[0][mainWidth-1] = '+', '+'
	grid[mainHeight-1][0], grid[mainHeight-1][mainWidth-1] = '+', '+'

	for rowIndex, rowCode := range rows {
		y := rowIndex + 1
		last := rowIndex == len(rows)-1
		east := rowIndex%2 == 0
		if east {
			startX := 1
			if rowIndex == 0 {
				grid[y][1], grid[y][2] = '@', '>'
				startX = 3
			} else {
				grid[y][1] = '>'
				startX = 2
			}
			copy(grid[y][startX:], rowCode)
			if last {
				grid[y][mainWidth-2] = 'H'
			} else {
				grid[y][mainWidth-2] = 'v'
			}
		} else {
			grid[y][mainWidth-2] = '<'
			copy(grid[y][2:], reverse(rowCode))
			if last {
				grid[y][1] = 'H'
			} else {
				grid[y][1] = 'v'
			}
		}
	}

	outputX := mainWidth + 2
	for x := outputX; x < outputX+3; x++ {
		grid[0][x] = '-'
		grid[2][x] = '-'
	}
	for y := 0; y < 3; y++ {
		grid[y][outputX] = '|'
		grid[y][outputX+2] = '|'
	}
	grid[0][outputX], grid[0][outputX+2] = '+', '+'
	grid[2][outputX], grid[2][outputX+2] = '+', '+'
	grid[1][outputX+1] = 'O'
	grid[1][mainWidth], grid[1][mainWidth+1] = '>', '>'

	lines := make([]string, len(grid))
	for index, row := range grid {
		lines[index] = strings.TrimRight(string(row), " ")
	}
	return strings.Join(lines, "\n") + "\n"
}

func main() {
	inputPath := flag.String("input", "", "text file to emit")
	outputPath := flag.String("output", "", "generated .man file")
	encoding := flag.String(
		"encoding",
		"arithmetic",
		"encoding: arithmetic, packed, base71-rom, base71-mapper, base75-rom, base75-mapper, "+
			"base92-rom, base99-rom, base99-pairs, base99-unpacker, base99-decoder, huffman, "+
			"huffman-rom, huffman-table, huffman-bit-unpacker, "+
			"huffman-bit-unpacker-rotated, huffman-code-relay, "+
			"huffman-table-unpacker, huffman-counts, huffman-canonical-decoder, "+
			"huffman-symbol-scanner, huffman-compact-decoder, or huffman-decoder",
	)
	decoderPath := flag.String("decoder-block", "", "packed decoder .block file")
	huffmanCandidates := flag.Int("huffman-candidates", 1024, "phrase candidates considered")
	huffmanMacros := flag.Int("huffman-macros", 96, "maximum selected phrase macros")
	huffmanMaxMacroLength := flag.Int(
		"huffman-max-macro-length",
		32,
		"maximum phrase macro length",
	)
	flag.Parse()
	if *inputPath == "" || *outputPath == "" {
		flag.Usage()
		os.Exit(2)
	}

	data, err := os.ReadFile(*inputPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read input: %v\n", err)
		os.Exit(1)
	}
	if *encoding == "base71-rom" || *encoding == "base71-mapper" {
		artifact, packErr := packBase71(data)
		if packErr != nil {
			fmt.Fprintf(os.Stderr, "pack base-71: %v\n", packErr)
			os.Exit(1)
		}
		var block []byte
		if *encoding == "base71-rom" {
			block, err = base71ROMBlock(artifact)
		} else {
			block, err = cyclicMapperBlock(artifact.Alphabet, 41)
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "generate %s: %v\n", *encoding, err)
			os.Exit(1)
		}
		if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
			fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
			os.Exit(1)
		}
		fmt.Printf(
			"generated %s for %d bytes in %d words\n",
			*encoding,
			len(data),
			len(artifact.Words),
		)
		return
	}
	if *encoding == "base99-rom" ||
		*encoding == "base99-pairs" ||
		*encoding == "base99-unpacker" ||
		*encoding == "base99-decoder" ||
		*encoding == "base99-decoder-mirror" ||
		*encoding == "base99-ascii-mirror" {
		artifact, packErr := packBase99(data)
		if packErr != nil {
			fmt.Fprintf(os.Stderr, "pack base-99: %v\n", packErr)
			os.Exit(1)
		}
		var block []byte
		switch *encoding {
		case "base99-rom":
			block, err = base99ROMBlock(artifact)
		case "base99-pairs":
			block, err = base99PairTableBlock(artifact)
		case "base99-unpacker":
			block, err = base99UnpackerBlock()
		case "base99-decoder":
			block, err = base99DigramDecoderBlock()
		case "base99-decoder-mirror":
			var original []byte
			original, err = base99DigramDecoderBlock()
			if err == nil {
				block, err = mirrorBase99Block(original, "base99_digram_decoder_mirror")
				if err == nil {
					var rotated base75MapperDefinition
					err = json.Unmarshal(block, &rotated)
					if err == nil {
						pairs := rotated.Ports["pairs"]
						pairs.Side = "top"
						pairs.OffsetRange = []int{8, 8}
						rotated.Ports["pairs"] = pairs
						block, err = marshalBase99Block(rotated)
					}
				}
			}
		case "base99-ascii-mirror":
			var original []byte
			original, err = base99ASCIIMapperBlock()
			if err == nil {
				block, err = mirrorBase99Block(original, "base99_ascii_mirror")
				if err == nil {
					block, err = base99ASCIIMirrorFloorSafe(block)
				}
			}
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "generate %s: %v\n", *encoding, err)
			os.Exit(1)
		}
		if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
			fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
			os.Exit(1)
		}
		fmt.Printf(
			"generated %s for %d bytes in %d tokens and %d words\n",
			*encoding,
			len(data),
			len(artifact.Tokens),
			len(artifact.Words),
		)
		return
	}
	if *encoding == "base92-rom" {
		artifact, packErr := packBase92(data)
		if packErr != nil {
			fmt.Fprintf(os.Stderr, "pack base-92: %v\n", packErr)
			os.Exit(1)
		}
		block, blockErr := base92ROMBlock(artifact)
		if blockErr != nil {
			fmt.Fprintf(os.Stderr, "generate base92-rom: %v\n", blockErr)
			os.Exit(1)
		}
		if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
			fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
			os.Exit(1)
		}
		fmt.Printf(
			"generated base92-rom for %d bytes in %d words\n",
			len(data),
			len(artifact.Words),
		)
		return
	}
	if *encoding == "base75-rom" || *encoding == "base75-mapper" {
		var block []byte
		if *encoding == "base75-rom" {
			artifact, packErr := packBase75(data)
			if packErr != nil {
				fmt.Fprintf(os.Stderr, "pack base-75: %v\n", packErr)
				os.Exit(1)
			}
			block, err = base75ROMBlock(artifact)
		} else {
			block, err = base75MapperBlock()
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "generate %s: %v\n", *encoding, err)
			os.Exit(1)
		}
		if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
			fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
			os.Exit(1)
		}
		fmt.Printf("generated %s for %d bytes\n", *encoding, len(data))
		return
	}
	if *encoding == "huffman" ||
		*encoding == "huffman-decoder" ||
		*encoding == "huffman-rom" ||
		*encoding == "huffman-table" ||
		*encoding == "huffman-bit-unpacker" ||
		*encoding == "huffman-bit-unpacker-rotated" ||
		*encoding == "huffman-code-relay" ||
		*encoding == "huffman-table-unpacker" ||
		*encoding == "huffman-counts" ||
		*encoding == "huffman-canonical-decoder" ||
		*encoding == "huffman-symbol-scanner" ||
		*encoding == "huffman-compact-decoder" {
		artifact := compressHuffman(
			data,
			*huffmanCandidates,
			*huffmanMacros,
			*huffmanMaxMacroLength,
		)
		if *encoding == "huffman-decoder" {
			source, sourceErr := huffmanDecoderSource(artifact)
			if sourceErr != nil {
				fmt.Fprintf(os.Stderr, "generate Huffman decoder: %v\n", sourceErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, []byte(source), 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			fmt.Printf(
				"generated decoder source for %d symbols (%d macros)\n",
				len(artifact.Symbols),
				artifact.MacroCount,
			)
			return
		}
		if *encoding == "huffman-rom" {
			block, blockErr := huffmanROMBlock(artifact)
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate Huffman ROM: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			fmt.Printf(
				"generated Huffman ROM with %d words\n",
				len(artifact.Words),
			)
			return
		}
		if *encoding == "huffman-table" {
			table, tableErr := huffmanTable(artifact)
			if tableErr != nil {
				fmt.Fprintf(os.Stderr, "build Huffman table: %v\n", tableErr)
				os.Exit(1)
			}
			block, blockErr := huffmanTableBlock(table)
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate Huffman table: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			fmt.Printf("generated Huffman symbol table with %d words\n", len(table.Words))
			return
		}
		if *encoding == "huffman-bit-unpacker" {
			block, blockErr := compactUnpackerBlock(
				"history_huffman_bit_unpacker",
				2,
				huffmanWordBits,
				"words",
				"bits",
				true,
			)
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate Huffman bit unpacker: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			return
		}
		if *encoding == "huffman-bit-unpacker-rotated" {
			block, blockErr := huffmanRotatedBitUnpackerBlock()
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate rotated Huffman bit unpacker: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			return
		}
		if *encoding == "huffman-code-relay" {
			block, blockErr := huffmanCodeRelayBlock()
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate Huffman code relay: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			return
		}
		if *encoding == "huffman-table-unpacker" {
			block, blockErr := huffmanTableUnpackerBlock()
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate Huffman table unpacker: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			return
		}
		if *encoding == "huffman-counts" {
			block, blockErr := huffmanCountsBlock(artifact)
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate Huffman counts: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			return
		}
		if *encoding == "huffman-canonical-decoder" {
			block, blockErr := huffmanCanonicalDecoderBlock(artifact)
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate canonical Huffman decoder: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			return
		}
		if *encoding == "huffman-symbol-scanner" {
			table, tableErr := huffmanTable(artifact)
			if tableErr != nil {
				fmt.Fprintf(os.Stderr, "build Huffman table: %v\n", tableErr)
				os.Exit(1)
			}
			block, blockErr := huffmanSymbolScannerBlock(artifact, table)
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate Huffman symbol scanner: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			return
		}
		if *encoding == "huffman-compact-decoder" {
			table, tableErr := huffmanTable(artifact)
			if tableErr != nil {
				fmt.Fprintf(os.Stderr, "build Huffman table: %v\n", tableErr)
				os.Exit(1)
			}
			block, blockErr := huffmanCompactDecoderBlock(artifact, table)
			if blockErr != nil {
				fmt.Fprintf(os.Stderr, "generate compact Huffman decoder: %v\n", blockErr)
				os.Exit(1)
			}
			if writeErr := os.WriteFile(*outputPath, block, 0o644); writeErr != nil {
				fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
				os.Exit(1)
			}
			return
		}

		encoded, marshalErr := json.MarshalIndent(artifact, "", "  ")
		if marshalErr != nil {
			fmt.Fprintf(os.Stderr, "encode Huffman artifact: %v\n", marshalErr)
			os.Exit(1)
		}
		encoded = append(encoded, '\n')
		if writeErr := os.WriteFile(*outputPath, encoded, 0o644); writeErr != nil {
			fmt.Fprintf(os.Stderr, "write output: %v\n", writeErr)
			os.Exit(1)
		}
		fmt.Printf(
			"compressed %d bytes into %d tokens, %d stream bits, and %d reverse-safe words; "+
				"%d macros use %d dictionary bytes; representation=%d bits\n",
			len(data),
			artifact.TokenCount,
			artifact.BitLength,
			len(artifact.Words),
			artifact.MacroCount,
			artifact.DictionaryBytes,
			artifact.RepresentationBits,
		)
		return
	}

	needed := make(map[byte]bool)
	for _, value := range data {
		needed[value] = true
	}

	var solution string
	var instructionCount int
	switch *encoding {
	case "arithmetic":
		programs := shortestBytePrograms(needed)
		var code strings.Builder
		for _, value := range data {
			code.WriteString(programs[value])
			code.WriteByte('s')
		}
		instructionCount = code.Len()
		solution = drawSolution(code.String())
	case "packed":
		if *decoderPath == "" {
			fmt.Fprintln(os.Stderr, "-decoder-block is required for packed encoding")
			os.Exit(2)
		}
		decoder, readErr := readBlock(*decoderPath)
		if readErr != nil {
			fmt.Fprintf(os.Stderr, "read decoder block: %v\n", readErr)
			os.Exit(1)
		}
		solution = drawPackedSolution(data, decoder)
	default:
		fmt.Fprintf(os.Stderr, "unknown encoding %q\n", *encoding)
		os.Exit(2)
	}
	if err := os.WriteFile(*outputPath, []byte(solution), 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write output: %v\n", err)
		os.Exit(1)
	}

	lines := strings.Split(strings.TrimSuffix(solution, "\n"), "\n")
	if *encoding == "arithmetic" {
		fmt.Printf(
			"encoded %d bytes into %d instructions; solution dimensions %dx%d\n",
			len(data),
			instructionCount,
			len(lines[0]),
			len(lines),
		)
	} else {
		fmt.Printf(
			"packed %d bytes; solution dimensions %dx%d\n",
			len(data),
			len(lines[0]),
			len(lines),
		)
	}
}
