package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

const (
	base71Radix         = int64(71)
	base71CharsPerWord  = 10
	base71WordsPerRow   = 4
	base71LiteralDigits = 19
	base71LiteralPitch  = base71LiteralDigits + 3
	base71FirstLiteral  = 2
	base71ROMWidth      = base71WordsPerRow*base71LiteralPitch + 3
)

var base71Alphabet = []byte{
	32, 97, 101, 110, 105, 111, 116, 114, 115, 108, 44, 100, 63, 99, 83, 117,
	104, 34, 48, 58, 102, 121, 103, 112, 59, 50, 65, 77, 72, 41, 52, 98, 49,
	82, 80, 107, 70, 74, 75, 68, 85, 118, 119, 51, 76, 45, 66, 71, 87, 78,
	79, 84, 40, 86, 109, 69, 106, 54, 55, 120, 57, 67, 53, 73, 56, 122, 46,
	90, 39, 81, 88,
}

type base71Artifact struct {
	Alphabet []byte
	Words    []int64
}

func packBase71(data []byte) (base71Artifact, error) {
	if len(data)%base71CharsPerWord != 0 {
		return base71Artifact{}, fmt.Errorf(
			"base-71 input length %d is not divisible by %d",
			len(data),
			base71CharsPerWord,
		)
	}
	ranks := make(map[byte]int64, len(base71Alphabet))
	for rank, value := range base71Alphabet {
		ranks[value] = int64(rank)
	}

	words := make([]int64, 0, len(data)/base71CharsPerWord)
	for start := 0; start < len(data); start += base71CharsPerWord {
		var word, place int64 = 0, 1
		for _, value := range data[start : start+base71CharsPerWord] {
			rank, found := ranks[value]
			if !found {
				return base71Artifact{}, fmt.Errorf("byte %d is not in the base-71 alphabet", value)
			}
			word += rank * place
			place *= base71Radix
		}
		digits := strconv.FormatInt(word, 10)
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			return base71Artifact{}, fmt.Errorf("word %d is not reverse-safe", word)
		}
		words = append(words, word)
	}
	return base71Artifact{
		Alphabet: append([]byte(nil), base71Alphabet...),
		Words:    words,
	}, nil
}

func unpackBase71(artifact base71Artifact) []byte {
	output := make([]byte, 0, len(artifact.Words)*base71CharsPerWord)
	for _, word := range artifact.Words {
		for range base71CharsPerWord {
			rank := word % base71Radix
			word /= base71Radix
			output = append(output, artifact.Alphabet[rank])
		}
	}
	return output
}

func base71ROMBlock(artifact base71Artifact) ([]byte, error) {
	rows := (len(artifact.Words) + base71WordsPerRow - 1) / base71WordsPerRow
	interior := make([]string, rows)

	for rowIndex := range rows {
		row := []byte(strings.Repeat(" ", base71ROMWidth))
		east := rowIndex%2 == 0
		last := rowIndex == rows-1
		start := rowIndex * base71WordsPerRow
		end := min(start+base71WordsPerRow, len(artifact.Words))

		if east {
			if rowIndex == 0 {
				row[0], row[1] = '@', '>'
			} else {
				row[0] = '>'
			}
			if !last {
				row[base71ROMWidth-1] = 'v'
			}
		} else {
			row[base71ROMWidth-1] = '<'
			if !last {
				row[0] = 'v'
			}
		}

		rowWords := artifact.Words[start:end]
		for logicalIndex, word := range rowWords {
			slot := logicalIndex
			if !east {
				slot = len(rowWords) - 1 - logicalIndex
			}
			left := base71FirstLiteral + slot*base71LiteralPitch
			digits := strconv.FormatInt(word, 10)
			if len(digits) > base71LiteralDigits {
				return nil, fmt.Errorf("base-71 word %d needs %d digits", word, len(digits))
			}
			if !east {
				digits = reverse(digits)
			}
			row[left], row[left+base71LiteralDigits+1] = '`', '`'
			copy(row[left+1:], digits)
			if east {
				row[left+base71LiteralDigits+2] = 's'
			} else {
				row[left-1] = 's'
			}
		}

		if last {
			lastSlot := len(rowWords) - 1
			if !east {
				lastSlot = 0
			}
			left := base71FirstLiteral + lastSlot*base71LiteralPitch
			if east {
				row[left+base71LiteralDigits+3] = 'H'
			} else {
				row[left-2] = 'H'
			}
		}
		interior[rowIndex] = string(row)
	}

	block := huffmanROMDefinition{
		Name:     "history_base71_rom",
		Size:     fmt.Sprintf("%dx%d", base71ROMWidth, rows),
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

func cyclicMapperBlock(alphabet []byte, width int) ([]byte, error) {
	needed := make(map[byte]bool, len(alphabet))
	for _, value := range alphabet {
		needed[value] = true
	}
	programs := shortestBytePrograms(needed)

	var code strings.Builder
	code.WriteString("1Ns")
	for _, value := range alphabet {
		code.WriteString(programs[value])
		code.WriteByte('s')
	}

	capacity := width - 4
	dataRows := (code.Len() + capacity - 1) / capacity
	interior := make([]string, dataRows+1)
	remaining := code.String()
	for rowIndex := range dataRows {
		row := []byte(strings.Repeat(" ", width))
		count := min(capacity, len(remaining))
		chunk := remaining[:count]
		remaining = remaining[count:]
		east := rowIndex%2 == 0
		if east {
			if rowIndex == 0 {
				row[0], row[1] = '>', '@'
			} else {
				row[1] = '>'
			}
			copy(row[2:], chunk)
			row[width-2] = 'v'
		} else {
			row[width-2] = '<'
			copy(row[width-2-len(chunk):], reverse(chunk))
			row[1] = 'v'
		}
		interior[rowIndex] = string(row)
	}

	returnRow := []byte(strings.Repeat(" ", width))
	returnRow[0] = '^'
	if (dataRows-1)%2 == 0 {
		returnRow[width-2] = '<'
	} else {
		returnRow[1] = '<'
	}
	interior[dataRows] = string(returnRow)

	block := huffmanROMDefinition{
		Name:     "base71_mapper",
		Size:     fmt.Sprintf("%dx%d", width, len(interior)),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"values": {
				Type:        "output",
				Side:        "left",
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

func equalBase71Data(artifact base71Artifact, data []byte) bool {
	return bytes.Equal(unpackBase71(artifact), data)
}
