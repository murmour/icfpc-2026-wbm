package main

import (
	"encoding/json"
	"fmt"
	"math"
	"slices"
	"strconv"
	"strings"
)

const (
	huffmanTableRadix        = int64(127)
	huffmanTableCodesPerWord = 9
	huffmanTableWordsPerRow  = 2
	huffmanTableDigits       = 19
	huffmanTablePitch        = huffmanTableDigits + 3
)

type huffmanTableArtifact struct {
	Words []int64
	Codes []int64
}

func canonicalSymbols(artifact huffmanArtifact) []huffmanSymbol {
	symbols := append([]huffmanSymbol(nil), artifact.Symbols...)
	sortHuffmanSymbols(symbols)
	return symbols
}

func sortHuffmanSymbols(symbols []huffmanSymbol) {
	slices.SortFunc(symbols, func(left, right huffmanSymbol) int {
		if left.BitLength != right.BitLength {
			return left.BitLength - right.BitLength
		}
		return strings.Compare(left.Code, right.Code)
	})
}

func huffmanTable(artifact huffmanArtifact) (huffmanTableArtifact, error) {
	codes := []int64{0}
	for _, symbol := range canonicalSymbols(artifact) {
		var values []byte
		switch symbol.Kind {
		case "byte":
			if symbol.Byte == nil {
				return huffmanTableArtifact{}, fmt.Errorf("byte symbol %d has no value", symbol.ID)
			}
			values = []byte{*symbol.Byte}
		case "macro":
			values = []byte(symbol.Text)
		case "eof":
		default:
			return huffmanTableArtifact{}, fmt.Errorf("unknown symbol kind %q", symbol.Kind)
		}
		for _, value := range values {
			if int64(value)+2 >= huffmanTableRadix {
				return huffmanTableArtifact{}, fmt.Errorf("byte %d does not fit table radix", value)
			}
			codes = append(codes, int64(value)+2)
		}
		codes = append(codes, 1)
	}
	for len(codes)%huffmanTableCodesPerWord != 0 {
		codes = append(codes, 1)
	}

	words := make([]int64, 0, len(codes)/huffmanTableCodesPerWord)
	for start := 0; start < len(codes); start += huffmanTableCodesPerWord {
		var word, place int64 = 0, 1
		for _, code := range codes[start : start+huffmanTableCodesPerWord] {
			word += code * place
			place *= huffmanTableRadix
		}
		if word < 0 || len(strconv.FormatInt(word, 10)) > huffmanTableDigits {
			return huffmanTableArtifact{}, fmt.Errorf("table word %d does not fit", word)
		}
		words = append(words, word)
	}
	return huffmanTableArtifact{Words: words, Codes: codes}, nil
}

func huffmanTableWordsFitSigned(artifact huffmanArtifact) bool {
	table, err := huffmanTable(artifact)
	if err != nil {
		return false
	}
	for _, word := range table.Words {
		digits := strconv.FormatInt(word, 10)
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			return false
		}
	}
	return true
}

func huffmanTableBlock(table huffmanTableArtifact) ([]byte, error) {
	rows := (len(table.Words) + huffmanTableWordsPerRow - 1) / huffmanTableWordsPerRow
	width := huffmanTableWordsPerRow*huffmanTablePitch + 4
	interior := make([]string, rows)

	for rowIndex := range rows {
		row := []byte(strings.Repeat(" ", width))
		east := rowIndex%2 == 0
		if east {
			if rowIndex == 0 {
				row[1], row[2] = '@', '>'
			} else {
				row[1] = '>'
			}
			row[width-1] = 'v'
		} else {
			row[width-1] = '<'
			row[1] = 'v'
		}

		start := rowIndex * huffmanTableWordsPerRow
		end := min(start+huffmanTableWordsPerRow, len(table.Words))
		rowWords := table.Words[start:end]
		for logicalIndex, word := range rowWords {
			slot := logicalIndex
			if !east {
				slot = len(rowWords) - 1 - logicalIndex
			}
			left := 3 + slot*huffmanTablePitch
			digits := strconv.FormatInt(word, 10)
			if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
				return nil, fmt.Errorf("table word %d is invalid in reverse: %w", word, err)
			}
			if !east {
				digits = reverse(digits)
			}
			row[left], row[left+huffmanTableDigits+1] = '`', '`'
			copy(row[left+1:], digits)
			if east {
				row[left+huffmanTableDigits+2] = 's'
			} else {
				row[left-1] = 's'
			}
		}
		interior[rowIndex] = string(row)
	}

	// Turn the final westbound row into a loop back to the first row.
	if rows%2 != 0 {
		return nil, fmt.Errorf("cyclic table requires an even row count, got %d", rows)
	}
	grid := make([][]byte, rows)
	for index, row := range interior {
		grid[index] = []byte(row)
		grid[index][0] = '^'
	}
	grid[0][0], grid[0][1], grid[0][2] = '>', '@', '>'
	grid[rows-1][1], grid[rows-1][0] = '<', '^'
	for index := range grid {
		reflected := make([]byte, width)
		for x, value := range grid[index] {
			switch value {
			case '>':
				value = '<'
			case '<':
				value = '>'
			}
			reflected[width-1-x] = value
		}
		interior[index] = string(reflected)
	}

	block := huffmanROMDefinition{
		Name:     "history_huffman_table",
		Size:     fmt.Sprintf("%dx%d", width, rows),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"words": {
				Type:        "output",
				Side:        "right",
				OffsetRange: []int{17, 17},
				LengthRange: []int{2, 4096},
			},
		},
	}
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func huffmanDepthValues(artifact huffmanArtifact) []int64 {
	maxLength := 0
	counts := make(map[int]int)
	for _, symbol := range artifact.Symbols {
		counts[symbol.BitLength]++
		maxLength = max(maxLength, symbol.BitLength)
	}
	var values []int64
	cumulative := 0
	for depth := 1; depth <= maxLength; depth++ {
		cumulative += counts[depth]
		values = append(values, int64(counts[depth]), int64(cumulative))
	}
	values = append(values, -1)
	return values
}

func unpackHuffmanTable(table huffmanTableArtifact) []int64 {
	result := make([]int64, 0, len(table.Words)*huffmanTableCodesPerWord)
	for _, original := range table.Words {
		word := original
		for range huffmanTableCodesPerWord {
			result = append(result, word%huffmanTableRadix)
			word /= huffmanTableRadix
		}
	}
	return result
}

func huffmanTableDimensions(table huffmanTableArtifact) (int, int) {
	rows := int(math.Ceil(float64(len(table.Words)) / huffmanTableWordsPerRow))
	return huffmanTableWordsPerRow*huffmanTablePitch + 6, rows + 2
}

func compactUnpackerBlock(
	name string,
	radix int64,
	outputCount int,
	inputName string,
	outputName string,
	remaindersOnly bool,
) ([]byte, error) {
	if outputCount < 2 {
		return nil, fmt.Errorf("unpacker output count must be at least two")
	}
	loopCount := outputCount - 1
	if remaindersOnly {
		loopCount = outputCount
	}
	countProgram := strconv.FormatInt(int64(loopCount), 10)
	if len(countProgram) > 1 {
		countProgram = "`" + countProgram + "`"
	}
	radixProgram := strconv.FormatInt(radix, 10)
	if len(radixProgram) > 1 {
		radixProgram = "`" + radixProgram + "`"
	}

	prefix := ">@rM" + countProgram + "bW>"
	loopTurn := len(prefix) - 1
	body := "M" + radixProgram + "W/WsWmd"
	suffix := "sv"
	if remaindersOnly {
		suffix = " v"
	}
	rowCode := prefix + body + suffix
	decrementX := len(prefix) + len(body) - 1
	exitX := decrementX + 2
	width := len(rowCode)
	interior := []string{
		strings.Repeat(" ", width),
		rowCode + strings.Repeat(" ", width-len(rowCode)),
		strings.Repeat(" ", loopTurn) + "^" +
			strings.Repeat(" ", decrementX-loopTurn-1) + "<" +
			strings.Repeat(" ", exitX-decrementX-1) + "v" +
			strings.Repeat(" ", width-exitX-1),
		"^" + strings.Repeat(" ", exitX-1) + "<" +
			strings.Repeat(" ", width-exitX-1),
	}

	expected := make([]int64, outputCount)
	value := int64(0)
	place := int64(1)
	for index := range outputCount {
		expected[index] = int64((index*7 + 1) % int(radix))
		value += expected[index] * place
		place *= radix
	}
	block := base75MapperDefinition{
		Name:     name,
		Size:     fmt.Sprintf("%dx4", width),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			inputName: {
				Type:        "input",
				Side:        "top",
				OffsetRange: []int{3, 3},
				LengthRange: []int{2, 4096},
			},
			outputName: {
				Type:        "output",
				Side:        "right",
				OffsetRange: []int{1, 1},
				LengthRange: []int{2, 4096},
			},
		},
		Tests: []base75BlockTest{{
			Name:     "one_word",
			Inputs:   map[string][]int64{inputName: {value}},
			Expected: map[string][]int64{outputName: expected},
		}},
	}
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func cyclicCodeBlock(name, outputName, code string, width int) ([]byte, error) {
	if width < 7 {
		return nil, fmt.Errorf("cyclic code width must be at least seven")
	}
	firstCapacity := width - 4
	rowCapacity := width - 3
	var chunks []string
	firstLength := min(firstCapacity, len(code))
	chunks = append(chunks, code[:firstLength])
	code = code[firstLength:]
	for len(code) > 0 {
		length := min(rowCapacity, len(code))
		chunks = append(chunks, code[:length])
		code = code[length:]
	}
	if len(chunks)%2 != 0 {
		chunks = append(chunks, "")
	}

	interior := make([]string, len(chunks))
	for rowIndex, chunk := range chunks {
		row := []byte(strings.Repeat(" ", width))
		row[0] = '^'
		if rowIndex%2 == 0 {
			if rowIndex == 0 {
				row[0], row[1], row[2] = '>', '@', '>'
				copy(row[3:], chunk)
			} else {
				row[1] = '>'
				copy(row[2:], chunk)
			}
			row[width-1] = 'v'
		} else {
			row[width-1] = '<'
			reversed := reverse(chunk)
			copy(row[2:], reversed)
			if rowIndex == len(chunks)-1 {
				row[1] = '<'
			} else {
				row[1] = 'v'
			}
		}
		interior[rowIndex] = string(row)
	}
	block := huffmanROMDefinition{
		Name:     name,
		Size:     fmt.Sprintf("%dx%d", width, len(interior)),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			outputName: {
				Type:        "output",
				Side:        "right",
				OffsetRange: []int{len(interior) / 2, len(interior) / 2},
				LengthRange: []int{2, 4096},
			},
		},
	}
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func huffmanCountsBlock(artifact huffmanArtifact) ([]byte, error) {
	values := huffmanDepthValues(artifact)
	needed := make(map[byte]bool)
	for _, value := range values {
		if value >= 0 {
			needed[byte(value)] = true
		}
	}
	programs := shortestBytePrograms(needed)
	var code strings.Builder
	for _, value := range values {
		if value < 0 {
			code.WriteString("1N")
		} else {
			code.WriteString(programs[byte(value)])
		}
		code.WriteByte('s')
	}
	raw, err := cyclicCodeBlock("history_huffman_counts", "values", code.String(), 7)
	if err != nil {
		return nil, err
	}
	var block huffmanROMDefinition
	if err := json.Unmarshal(raw, &block); err != nil {
		return nil, err
	}
	port := block.Ports["values"]
	port.Side = "bottom"
	port.OffsetRange = []int{6, 6}
	block.Ports["values"] = port
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func huffmanCanonicalDecoderBlock(artifact huffmanArtifact) ([]byte, error) {
	const width, height = 26, 5
	grid := make([][]byte, height)
	for row := range grid {
		grid[row] = []byte(strings.Repeat(" ", width))
	}
	put := func(x, y int, code string) {
		copy(grid[y][x:], code)
	}

	grid[0][0], grid[0][21], grid[0][25] = 'v', '<', '<'
	grid[1][0], grid[1][25] = 'v', '^'
	put(19, 1, ">r^")
	put(0, 2, ">@rN++M")
	put(12, 2, "r+M1--NX")
	grid[2][25] = 'M'
	put(10, 3, "vMN1s-rMW<vMN1<0")
	grid[4][10] = '>'
	put(20, 4, ">rW-X^")

	interior := make([]string, height)
	for row := range grid {
		interior[row] = string(grid[row])
	}

	var bits []int64
	var expected []int64
	depthCycle := huffmanDepthValues(artifact)
	var depthValues []int64
	for rank, symbol := range canonicalSymbols(artifact) {
		for _, bit := range symbol.Code {
			bits = append(bits, int64(bit-'0'))
		}
		depthValues = append(depthValues, depthCycle...)
		expected = append(expected, int64(rank))
	}

	block := base75MapperDefinition{
		Name:     "history_huffman_canonical_decoder",
		Size:     fmt.Sprintf("%dx%d", width, height),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"bits": {
				Type:        "input",
				Side:        "left",
				OffsetRange: []int{2, 2},
				LengthRange: []int{2, 4096},
			},
			"depths": {
				Type:        "input",
				Side:        "top",
				OffsetRange: []int{20, 20},
				LengthRange: []int{2, 4096},
			},
			"ranks": {
				Type:        "output",
				Side:        "bottom",
				OffsetRange: []int{14, 14},
				LengthRange: []int{2, 4096},
			},
		},
		Tests: []base75BlockTest{{
			Name: "all_symbols",
			Inputs: map[string][]int64{
				"bits":   bits,
				"depths": depthValues,
			},
			Expected: map[string][]int64{"ranks": expected},
		}},
	}
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func huffmanSymbolScannerBlock(artifact huffmanArtifact, table huffmanTableArtifact) ([]byte, error) {
	const width, height = 20, 5
	grid := make([][]byte, height)
	for row := range grid {
		grid[row] = []byte(strings.Repeat(" ", width))
	}
	put := func(x, y int, code string) {
		copy(grid[y][x:], code)
	}

	grid[0][0], grid[0][17] = 'v', '<'
	put(15, 1, ">d^")
	put(0, 2, ">@rb>rX")
	put(8, 2, ">rM1W-X^v")
	grid[3][4], grid[3][6], grid[3][8] = '^', '<', '^'
	put(14, 3, ">dm-sv")
	grid[4][8], grid[4][15], grid[4][16], grid[4][19] = '^', '<', '<', '<'

	interior := make([]string, height)
	for row := range grid {
		interior[row] = string(grid[row])
	}

	symbols := canonicalSymbols(artifact)
	testRanks := []int{0, len(symbols) / 2, len(symbols) - 1}
	var codes, expected []int64
	for _, rank := range testRanks {
		codes = append(codes, table.Codes...)
		expected = append(expected, symbolOutput(symbols[rank])...)
	}
	ranks := make([]int64, len(testRanks))
	for index, rank := range testRanks {
		ranks[index] = int64(rank)
	}

	block := base75MapperDefinition{
		Name:     "history_huffman_symbol_scanner",
		Size:     fmt.Sprintf("%dx%d", width, height),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"ranks": {
				Type:        "input",
				Side:        "left",
				OffsetRange: []int{2, 2},
				LengthRange: []int{2, 4096},
			},
			"codes": {
				Type:        "input",
				Side:        "top",
				OffsetRange: []int{7, 7},
				LengthRange: []int{2, 4096},
			},
			"bytes": {
				Type:        "output",
				Side:        "right",
				OffsetRange: []int{3, 3},
				LengthRange: []int{2, 4096},
			},
		},
		Tests: []base75BlockTest{{
			Name: "byte_macro_eof",
			Inputs: map[string][]int64{
				"ranks": ranks,
				"codes": codes,
			},
			Expected: map[string][]int64{"bytes": expected},
		}},
	}
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func symbolOutput(symbol huffmanSymbol) []int64 {
	switch symbol.Kind {
	case "byte":
		if symbol.Byte == nil {
			return nil
		}
		return []int64{int64(*symbol.Byte)}
	case "macro":
		result := make([]int64, len(symbol.Text))
		for index, value := range []byte(symbol.Text) {
			result[index] = int64(value)
		}
		return result
	default:
		return nil
	}
}

func rotateHalfTurn(rows []string) []string {
	height := len(rows)
	width := 0
	for _, row := range rows {
		width = max(width, len(row))
	}
	result := make([]string, height)
	rotate := func(value byte) byte {
		switch value {
		case '>':
			return '<'
		case '<':
			return '>'
		case '^':
			return 'v'
		case 'v':
			return '^'
		default:
			return value
		}
	}
	for y := range height {
		row := []byte(strings.Repeat(" ", width))
		source := rows[height-1-y]
		for x := range width {
			sourceX := width - 1 - x
			if sourceX < len(source) {
				row[x] = rotate(source[sourceX])
			}
		}
		result[y] = string(row)
	}
	return result
}

func huffmanCompactDecoderBlock(
	artifact huffmanArtifact,
	table huffmanTableArtifact,
) ([]byte, error) {
	const width, height = 23, 12
	grid := make([][]byte, height)
	for row := range grid {
		grid[row] = []byte(strings.Repeat(" ", width))
	}
	put := func(x, y int, code string) {
		copy(grid[y][x:], code)
	}

	// Canonical decoder.
	grid[0][0], grid[0][17], grid[0][22] = 'v', '<', '<'
	grid[1][0], grid[1][22] = 'v', '^'
	put(17, 1, "^r <")
	put(0, 2, ">@rN++M")
	put(13, 2, "r+M1--NX")
	grid[2][22] = 'M'
	put(9, 3, "vM1b+1M-rMW<")
	put(22, 3, "0")
	grid[4][9] = '>'
	put(18, 4, ">r+Xd")

	// The depth-sync path has BP=rank+1; scanner completion has BP<0.
	put(16, 5, "vmX  <d")

	scannerRows := []string{
		"v                <  ",
		"               >d^  ",
		">@rb>rX >rM1W-X^v   ",
		"    ^ < ^     >dm-sv",
		"        ^      <<  <",
	}
	rotated := rotateHalfTurn(scannerRows)
	for rowIndex, row := range rotated {
		copy(grid[6+rowIndex][3:], row)
	}

	// Enter after the scanner's removed rank receive/backpack setup.
	grid[8][22], grid[8][21], grid[8][20], grid[8][19] = '^', ' ', ' ', ' '
	grid[8][18] = '<'
	put(16, 6, "> v")
	grid[7][18] = 'v'

	// Scanner completion climbs the right edge and decrements BP for EOF.
	grid[10][22] = '^'
	grid[9][22] = 'm'
	grid[7][22] = '^'
	grid[6][22] = '^'

	interior := make([]string, height)
	for row := range grid {
		interior[row] = string(grid[row])
	}

	symbols := canonicalSymbols(artifact)
	testRanks := []int{0, len(symbols) / 2, len(symbols) - 1}
	var tests []base75BlockTest
	depthCycle := huffmanDepthValues(artifact)
	for _, rank := range testRanks {
		var bits []int64
		for _, bit := range symbols[rank].Code {
			bits = append(bits, int64(bit-'0'))
		}
		tests = append(tests, base75BlockTest{
			Name: fmt.Sprintf("rank_%d", rank),
			Inputs: map[string][]int64{
				"bits":   bits,
				"depths": depthCycle,
				"codes":  table.Codes,
			},
			Expected: map[string][]int64{"bytes": symbolOutput(symbols[rank])},
		})
	}
	var sequenceBits, sequenceDepths, sequenceCodes, sequenceExpected []int64
	for _, rank := range testRanks {
		for _, bit := range symbols[rank].Code {
			sequenceBits = append(sequenceBits, int64(bit-'0'))
		}
		sequenceDepths = append(sequenceDepths, depthCycle...)
		sequenceCodes = append(sequenceCodes, table.Codes...)
		sequenceExpected = append(sequenceExpected, symbolOutput(symbols[rank])...)
	}
	tests = append(tests, base75BlockTest{
		Name: "rank_sequence",
		Inputs: map[string][]int64{
			"bits":   sequenceBits,
			"depths": sequenceDepths,
			"codes":  sequenceCodes,
		},
		Expected: map[string][]int64{"bytes": sequenceExpected},
	})

	block := base75MapperDefinition{
		Name:     "history_huffman_compact_decoder",
		Size:     fmt.Sprintf("%dx%d", width, height),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"bits": {
				Type:        "input",
				Side:        "left",
				OffsetRange: []int{2, 2},
				LengthRange: []int{2, 4096},
			},
			"depths": {
				Type:        "input",
				Side:        "top",
				OffsetRange: []int{22, 22},
				LengthRange: []int{2, 4096},
			},
			"codes": {
				Type:        "input",
				Side:        "right",
				OffsetRange: []int{8, 8},
				LengthRange: []int{2, 4096},
			},
			"bytes": {
				Type:        "output",
				Side:        "left",
				OffsetRange: []int{7, 7},
				LengthRange: []int{2, 4096},
			},
		},
		Tests: tests,
	}
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func huffmanTableUnpackerBlock() ([]byte, error) {
	raw, err := compactUnpackerBlock(
		"history_huffman_table_unpacker",
		huffmanTableRadix,
		huffmanTableCodesPerWord,
		"words",
		"codes",
		false,
	)
	if err != nil {
		return nil, err
	}
	var block base75MapperDefinition
	if err := json.Unmarshal(raw, &block); err != nil {
		return nil, err
	}
	width, height, err := parseSize(block.Size)
	if err != nil {
		return nil, err
	}
	block.Interior = block.Interior[1:]
	block.Size = fmt.Sprintf("%dx%d", width, height-1)
	input := block.Ports["words"]
	input.Side, input.OffsetRange = "left", []int{2, 2}
	block.Ports["words"] = input
	output := block.Ports["codes"]
	output.Side, output.OffsetRange = "right", []int{0, 0}
	block.Ports["codes"] = output
	encoded, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(encoded, '\n'), nil
}

func rotateBlockClockwise(raw []byte, name string) ([]byte, error) {
	var block base75MapperDefinition
	if err := json.Unmarshal(raw, &block); err != nil {
		return nil, err
	}
	width, height, err := parseSize(block.Size)
	if err != nil {
		return nil, err
	}
	grid := make([][]byte, width)
	for y := range grid {
		grid[y] = []byte(strings.Repeat(" ", height))
	}
	rotate := func(value byte) byte {
		switch value {
		case '>':
			return 'v'
		case 'v':
			return '<'
		case '<':
			return '^'
		case '^':
			return '>'
		default:
			return value
		}
	}
	for y, row := range block.Interior {
		for x := range width {
			if x < len(row) {
				grid[x][height-1-y] = rotate(row[x])
			}
		}
	}
	block.Name = name
	block.Size = fmt.Sprintf("%dx%d", height, width)
	block.Interior = make([]string, width)
	for row := range grid {
		block.Interior[row] = string(grid[row])
	}
	block.Tests = nil
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func huffmanRotatedBitUnpackerBlock() ([]byte, error) {
	raw, err := compactUnpackerBlock(
		"history_huffman_bit_unpacker",
		2,
		huffmanWordBits,
		"words",
		"bits",
		true,
	)
	if err != nil {
		return nil, err
	}
	rotated, err := rotateBlockClockwise(raw, "history_huffman_bit_unpacker_rotated")
	if err != nil {
		return nil, err
	}
	var block base75MapperDefinition
	if err := json.Unmarshal(rotated, &block); err != nil {
		return nil, err
	}
	var original base75MapperDefinition
	if err := json.Unmarshal(raw, &original); err != nil {
		return nil, err
	}
	firstRow := []byte(block.Interior[0])
	secondRow := []byte(block.Interior[1])
	firstRow[3], secondRow[3] = '<', '^'
	block.Interior[0], block.Interior[1] = string(firstRow), string(secondRow)
	input := block.Ports["words"]
	input.Side, input.OffsetRange = "left", []int{2, 2}
	block.Ports["words"] = input
	outputPort := block.Ports["bits"]
	outputPort.Side, outputPort.OffsetRange = "left", []int{21, 21}
	block.Ports["bits"] = outputPort
	block.Tests = original.Tests
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func huffmanCodeRelayBlock() ([]byte, error) {
	block := base75MapperDefinition{
		Name: "history_huffman_code_relay",
		Size: "3x2",
		Interior: []string{
			">@v",
			"^sU",
		},
		Ports: map[string]huffmanROMPort{
			"in": {
				Type:        "input",
				Side:        "right",
				OffsetRange: []int{1, 1},
				LengthRange: []int{2, 4096},
			},
			"out": {
				Type:        "output",
				Side:        "bottom",
				OffsetRange: []int{0, 0},
				LengthRange: []int{2, 4096},
			},
		},
		Tests: []base75BlockTest{{
			Name:     "relay",
			Inputs:   map[string][]int64{"in": {0, 42, 125}},
			Expected: map[string][]int64{"out": {0, 42, 125}},
		}},
	}
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}
