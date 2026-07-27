package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

const (
	packedCharsPerWord = 9
	romWordsPerRow     = 4
	romLiteralDigits   = 19
	romLiteralPitch    = 22
	romFirstLiteral    = 2
	packedPaddingByte  = 1
	packedEOFByte      = 2
)

type packedWord struct {
	value int64
}

type blockDef struct {
	Size     string   `json:"size"`
	Interior []string `json:"interior"`
}

type gridPoint struct {
	x int
	y int
}

func readBlock(path string) (blockDef, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return blockDef{}, err
	}
	var block blockDef
	if err := json.Unmarshal(data, &block); err != nil {
		return blockDef{}, err
	}
	return block, nil
}

func packASCII(data []byte) []packedWord {
	for _, char := range data {
		if char >= 128 {
			panic(fmt.Sprintf("byte %d is not 7-bit ASCII", char))
		}
	}

	const unreachable = int(^uint(0) >> 2)
	best := make([]int, len(data)+1)
	choice := make([]int, len(data))
	for index := range best {
		best[index] = unreachable
	}

	// The final word always contains eight bytes and EOF in its ninth slot.
	if len(data) >= packedCharsPerWord-1 {
		start := len(data) - (packedCharsPerWord - 1)
		if _, ok := packASCIIWord(data[start:], packedEOFByte); ok {
			best[start] = 1
			choice[start] = packedCharsPerWord - 1
		}
	}

	for index := len(data) - packedCharsPerWord; index >= 0; index-- {
		for _, count := range []int{packedCharsPerWord, packedCharsPerWord - 1} {
			next := index + count
			if next > len(data) || best[next] == unreachable {
				continue
			}
			control := byte(0)
			if count == packedCharsPerWord-1 {
				control = packedPaddingByte
			}
			if _, ok := packASCIIWord(data[index:next], control); !ok {
				continue
			}
			if best[next]+1 < best[index] {
				best[index] = best[next] + 1
				choice[index] = count
			}
		}
	}
	if best[0] == unreachable {
		panic("could not split text into reverse-safe packed words")
	}

	words := make([]packedWord, 0, best[0])
	for index := 0; index < len(data); {
		count := choice[index]
		control := byte(0)
		if index+count == len(data) {
			control = packedEOFByte
		} else if count == packedCharsPerWord-1 {
			control = packedPaddingByte
		}
		value, ok := packASCIIWord(data[index:index+count], control)
		if !ok {
			panic("selected packed word is not reverse-safe")
		}
		words = append(words, packedWord{value: value})
		index += count
	}
	return words
}

func packASCIIWord(data []byte, control byte) (int64, bool) {
	if len(data) != packedCharsPerWord && len(data) != packedCharsPerWord-1 {
		return 0, false
	}
	var value int64
	for index, char := range data {
		value |= int64(char) << (7 * index)
	}
	if len(data) == packedCharsPerWord-1 {
		value |= int64(control) << (7 * len(data))
	}
	digits := strconv.FormatInt(value, 10)
	if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
		return 0, false
	}
	return value, true
}

func parseSize(size string) (int, int, error) {
	var width, height int
	if _, err := fmt.Sscanf(size, "%dx%d", &width, &height); err != nil {
		return 0, 0, err
	}
	return width, height, nil
}

func newGrid(width, height int) [][]byte {
	grid := make([][]byte, height)
	for y := range grid {
		grid[y] = []byte(strings.Repeat(" ", width))
	}
	return grid
}

func drawRoom(grid [][]byte, x, y, interiorWidth, interiorHeight int, interior []string) {
	width, height := interiorWidth+2, interiorHeight+2
	for offset := 0; offset < width; offset++ {
		grid[y][x+offset] = '-'
		grid[y+height-1][x+offset] = '-'
	}
	for offset := 0; offset < height; offset++ {
		grid[y+offset][x] = '|'
		grid[y+offset][x+width-1] = '|'
	}
	grid[y][x], grid[y][x+width-1] = '+', '+'
	grid[y+height-1][x], grid[y+height-1][x+width-1] = '+', '+'
	for rowIndex, row := range interior {
		copy(grid[y+1+rowIndex][x+1:], row)
	}
}

func appendSegment(path []gridPoint, destination gridPoint) []gridPoint {
	current := path[len(path)-1]
	dx, dy := 0, 0
	if destination.x > current.x {
		dx = 1
	} else if destination.x < current.x {
		dx = -1
	} else if destination.y > current.y {
		dy = 1
	} else if destination.y < current.y {
		dy = -1
	}
	for current != destination {
		current = gridPoint{x: current.x + dx, y: current.y + dy}
		path = append(path, current)
	}
	return path
}

func drawPipe(grid [][]byte, path []gridPoint, destinationBorder gridPoint) {
	for index, point := range path {
		next := destinationBorder
		if index+1 < len(path) {
			next = path[index+1]
		}
		switch {
		case next.x > point.x:
			grid[point.y][point.x] = '>'
		case next.x < point.x:
			grid[point.y][point.x] = '<'
		case next.y > point.y:
			grid[point.y][point.x] = 'v'
		case next.y < point.y:
			grid[point.y][point.x] = '^'
		}
	}
}

func placePackedLiteral(row []byte, left int, word packedWord, east bool) {
	digits := strconv.FormatInt(word.value, 10)
	if !east {
		digits = reverse(digits)
	}
	row[left], row[left+romLiteralDigits+1] = '`', '`'
	copy(row[left+1:left+1+romLiteralDigits], strings.Repeat(" ", romLiteralDigits))
	copy(row[left+1:], digits)

	if east {
		right := left + romLiteralDigits + 1
		row[right+1] = 's'
	} else {
		row[left-1] = 's'
	}
}

func drawPackedROM(grid [][]byte, words []packedWord, rows int, interiorWidth int) {
	interior := make([]string, rows)

	for rowIndex := 0; rowIndex < rows; rowIndex++ {
		row := []byte(strings.Repeat(" ", interiorWidth))
		east := rowIndex%2 == 0
		last := rowIndex == rows-1
		if east {
			if rowIndex == 0 {
				row[0], row[1] = '@', '>'
			} else {
				row[0] = '>'
			}
			if !last {
				row[interiorWidth-1] = 'v'
			}
		} else {
			row[interiorWidth-1] = '<'
			if !last {
				row[0] = 'v'
			}
		}

		start := rowIndex * romWordsPerRow
		end := min(start+romWordsPerRow, len(words))
		rowWords := words[start:end]
		for logicalIndex, word := range rowWords {
			slot := logicalIndex
			if !east {
				slot = len(rowWords) - 1 - logicalIndex
			}
			left := romFirstLiteral + slot*romLiteralPitch
			placePackedLiteral(row, left, word, east)
		}
		if last {
			lastSlot := len(rowWords) - 1
			if !east {
				lastSlot = 0
			}
			left := romFirstLiteral + lastSlot*romLiteralPitch
			if east {
				row[left+romLiteralDigits+3] = 'H'
			} else {
				row[left-2] = 'H'
			}
		}
		interior[rowIndex] = string(row)
	}
	drawRoom(grid, 0, 0, interiorWidth, rows, interior)
}

func drawPackedSolution(data []byte, decoder blockDef) string {
	decoderWidth, decoderHeight, err := parseSize(decoder.Size)
	if err != nil {
		panic(fmt.Sprintf("parse decoder size: %v", err))
	}
	if decoderWidth != 28 || decoderHeight != 4 {
		panic(fmt.Sprintf("decoder geometry changed to %dx%d", decoderWidth, decoderHeight))
	}

	words := packASCII(data)
	romRows := (len(words) + romWordsPerRow - 1) / romWordsPerRow
	romInteriorWidth := romLiteralPitch*romWordsPerRow + 3
	romWidth, romHeight := romInteriorWidth+2, romRows+2

	decoderX, decoderY := 0, romHeight+3
	outputX, outputY := 34, decoderY+3
	totalWidth := romWidth
	totalHeight := decoderY + decoderHeight + 2
	grid := newGrid(totalWidth, totalHeight)

	drawPackedROM(grid, words, romRows, romInteriorWidth)
	drawRoom(grid, decoderX, decoderY, decoderWidth, decoderHeight, decoder.Interior)
	drawRoom(grid, outputX, outputY, 1, 1, []string{"O"})

	// ROM output to decoder rom input.
	drawPipe(grid,
		[]gridPoint{
			{x: 3, y: romHeight},
			{x: 3, y: romHeight + 1},
			{x: 3, y: romHeight + 2},
		},
		gridPoint{x: 3, y: decoderY},
	)

	// Decoder bytes output to O.
	path := []gridPoint{
		{x: 27, y: decoderY - 1},
		{x: 27, y: decoderY - 2},
	}
	path = appendSegment(path, gridPoint{x: 35, y: decoderY - 2})
	path = appendSegment(path, gridPoint{x: 35, y: outputY - 1})
	drawPipe(grid, path, gridPoint{x: 35, y: outputY})

	lines := make([]string, len(grid))
	for index, row := range grid {
		lines[index] = strings.TrimRight(string(row), " ")
	}
	return strings.Join(lines, "\n") + "\n"
}
