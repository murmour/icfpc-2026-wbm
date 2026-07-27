package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

const (
	base75Radix         = int64(75)
	base75CodesPerWord  = 9
	base75WordsPerRow   = 4
	base75LiteralDigits = 17
	base75LiteralPitch  = base75LiteralDigits + 3
	base75FirstLiteral  = 2
	base75ROMWidth      = base75WordsPerRow*base75LiteralPitch + 3
	base75CommaCode     = int64(17)
	base75MacroCode     = int64(74)
)

var base75PunctuationCodes = map[byte]int64{
	' ':  65,
	'"':  66,
	'\'': 67,
	'(':  68,
	')':  69,
	',':  70,
	'-':  71,
	'.':  72,
	'?':  73,
}

type base75Artifact struct {
	Words []int64
}

type base75BlockTest struct {
	Name     string             `json:"name"`
	Inputs   map[string][]int64 `json:"inputs"`
	Expected map[string][]int64 `json:"expected"`
}

type base75MapperDefinition struct {
	Name     string                    `json:"name"`
	Size     string                    `json:"size"`
	Interior []string                  `json:"interior"`
	Ports    map[string]huffmanROMPort `json:"ports"`
	Tests    []base75BlockTest         `json:"tests"`
}

func base75Code(value byte) (int64, bool) {
	switch {
	case value >= 'a' && value <= 'z':
		return int64(value-'a') + 1, true
	case value >= 'A' && value <= 'Z':
		return int64(value-'A') + 27, true
	case value >= '0' && value <= ';':
		return int64(value) + 5, true
	default:
		code, found := base75PunctuationCodes[value]
		return code, found
	}
}

func tokenizeBase75(data []byte) ([]int64, error) {
	tokens := make([]int64, 0, len(data))
	for index := 0; index < len(data); {
		if index+5 <= len(data) && string(data[index:index+5]) == " and " {
			tokens = append(tokens, base75MacroCode)
			index += 5
			continue
		}
		commaBeforeAnd := index+6 <= len(data) &&
			string(data[index:index+6]) == ", and "
		if index+2 <= len(data) &&
			string(data[index:index+2]) == ", " &&
			!commaBeforeAnd {
			tokens = append(tokens, base75CommaCode)
			index += 2
			continue
		}
		code, found := base75Code(data[index])
		if !found {
			return nil, fmt.Errorf("byte %d is outside the base-75 alphabet", data[index])
		}
		tokens = append(tokens, code)
		index++
	}
	return tokens, nil
}

func packBase75(data []byte) (base75Artifact, error) {
	tokens, err := tokenizeBase75(data)
	if err != nil {
		return base75Artifact{}, err
	}
	words := make([]int64, 0, (len(tokens)+base75CodesPerWord-1)/base75CodesPerWord)
	for start := 0; start < len(tokens); start += base75CodesPerWord {
		end := min(start+base75CodesPerWord, len(tokens))
		var word, place int64 = 0, 1
		for _, code := range tokens[start:end] {
			word += code * place
			place *= base75Radix
		}
		digits := strconv.FormatInt(word, 10)
		if len(digits) > base75LiteralDigits {
			return base75Artifact{}, fmt.Errorf("base-75 word %d needs %d digits", word, len(digits))
		}
		words = append(words, word)
	}
	return base75Artifact{Words: words}, nil
}

func base75Byte(code int64) ([]byte, bool) {
	switch {
	case code == 0:
		return nil, true
	case code == base75CommaCode:
		return []byte(", "), true
	case code >= 1 && code <= 26:
		return []byte{byte(code + 96)}, true
	case code >= 27 && code <= 52:
		return []byte{byte(code + 38)}, true
	case code >= 53 && code <= 64:
		return []byte{byte(code - 5)}, true
	case code == base75MacroCode:
		return []byte(" and "), true
	default:
		for value, candidate := range base75PunctuationCodes {
			if candidate == code {
				return []byte{value}, true
			}
		}
		return nil, false
	}
}

func unpackBase75(artifact base75Artifact) []byte {
	output := make([]byte, 0, len(artifact.Words)*base75CodesPerWord)
	for _, original := range artifact.Words {
		word := original
		for range base75CodesPerWord {
			code := word % base75Radix
			word /= base75Radix
			value, found := base75Byte(code)
			if !found {
				panic(fmt.Sprintf("invalid base-75 code %d", code))
			}
			output = append(output, value...)
		}
	}
	return output
}

func base75ROMBlock(artifact base75Artifact) ([]byte, error) {
	rows := (len(artifact.Words) + base75WordsPerRow - 1) / base75WordsPerRow
	interior := make([]string, rows)
	for rowIndex := range rows {
		row := []byte(strings.Repeat(" ", base75ROMWidth))
		east := rowIndex%2 == 0
		last := rowIndex == rows-1
		if east {
			if rowIndex == 0 {
				row[0], row[1] = '@', '>'
			} else {
				row[0] = '>'
			}
			if !last {
				row[base75ROMWidth-1] = 'v'
			}
		} else {
			row[base75ROMWidth-1] = '<'
			if !last {
				row[0] = 'v'
			}
		}

		start := rowIndex * base75WordsPerRow
		end := min(start+base75WordsPerRow, len(artifact.Words))
		rowWords := artifact.Words[start:end]
		for logicalIndex, word := range rowWords {
			slot := logicalIndex
			if !east {
				slot = len(rowWords) - 1 - logicalIndex
			}
			left := base75FirstLiteral + slot*base75LiteralPitch
			digits := strconv.FormatInt(word, 10)
			if !east {
				digits = reverse(digits)
			}
			row[left], row[left+base75LiteralDigits+1] = '`', '`'
			copy(row[left+1:], digits)
			if east {
				row[left+base75LiteralDigits+2] = 's'
			} else {
				row[left-1] = 's'
			}
		}

		if last {
			lastSlot := len(rowWords) - 1
			if !east {
				lastSlot = 0
			}
			left := base75FirstLiteral + lastSlot*base75LiteralPitch
			if east {
				row[left+base75LiteralDigits+3] = 'H'
			} else {
				row[left-2] = 'H'
			}
		}
		interior[rowIndex] = string(row)
	}

	block := huffmanROMDefinition{
		Name:     "history_base75_rom",
		Size:     fmt.Sprintf("%dx%d", base75ROMWidth, rows),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"words": {
				Type:        "output",
				Side:        "bottom",
				OffsetRange: []int{3, 3},
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

func base75MapperBlock() ([]byte, error) {
	const width, height = 43, 7
	grid := make([][]byte, height)
	for row := range grid {
		grid[row] = []byte(strings.Repeat(" ", width))
	}
	put := func(x, y int, code string) {
		copy(grid[y][x:], code)
	}

	put(0, 0, "v<")
	put(11, 0, "<")
	put(38, 0, "<")
	put(40, 0, "<")
	put(42, 0, "<")

	put(0, 1, ">@rX")
	put(11, 1, "^")
	put(40, 1, "^")

	put(1, 2, "^")
	put(3, 2, ">M1W-M`26`W/XWM`16`W-M*ba")
	put(32, 2, "`44`s`32`s^")

	put(1, 3, "^")
	put(15, 3, "b")
	put(42, 3, "<")

	put(1, 4, "^")
	put(7, 4, "s+`56`MW")
	put(15, 4, "xWM`12`W/XWM`48`+s")
	put(38, 4, "^>")
	put(42, 4, "^")

	put(0, 5, ">")
	put(24, 5, ">WM9W-")
	grid[5][39], grid[5][40] = 'X', 'v'

	lookup := "+M7*M`4565723557258711328`}M`127`W&s"
	for index := 0; index <= 25; index++ {
		grid[3][41-index] = lookup[index]
	}
	grid[3][15] = 'b'
	for index := 26; index < len(lookup); index++ {
		grid[3][14-(index-26)] = lookup[index]
	}

	lowercase := "WM`113`+s"
	grid[1][27] = '<'
	for index := range lowercase {
		grid[1][26-index] = lowercase[index]
	}

	macro := "`32`s`97`s`110`s`100`s`32`s"
	for index := range macro {
		grid[6][39-index] = macro[index]
	}
	grid[6][1], grid[6][40] = '^', '<'

	interior := make([]string, height)
	for row := range grid {
		interior[row] = string(grid[row])
	}
	block := base75MapperDefinition{
		Name:     "base75_ascii",
		Size:     fmt.Sprintf("%dx%d", width, height),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"codes": {
				Type:        "input",
				Side:        "left",
				OffsetRange: []int{1, 1},
				LengthRange: []int{2, 64},
			},
			"bytes": {
				Type:        "output",
				Side:        "right",
				OffsetRange: []int{3, 3},
				LengthRange: []int{2, 64},
			},
		},
		Tests: []base75BlockTest{
			{
				Name: "alphabet_and_macro",
				Inputs: map[string][]int64{
					"codes": {
						1, 16, 17, 18, 26, 27, 52, 53, 64,
						65, 66, 67, 68, 69, 70, 71, 72, 73,
						74, 0,
					},
				},
				Expected: map[string][]int64{
					"bytes": {
						97, 112, 44, 32, 114, 122, 65, 90, 48, 59,
						32, 34, 39, 40, 41, 44, 45, 46, 63,
						32, 97, 110, 100, 32,
					},
				},
			},
		},
	}
	output, err := json.MarshalIndent(block, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(output, '\n'), nil
}

func equalBase75Data(artifact base75Artifact, data []byte) bool {
	return bytes.Equal(unpackBase75(artifact), data)
}
