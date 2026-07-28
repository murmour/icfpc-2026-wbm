package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

const (
	base92Radix         = int64(92)
	base92CharsPerWord  = 9
	base92WordsPerRow   = 4
	base92LiteralDigits = 18
	base92LiteralPitch  = base92LiteralDigits + 3
	base92FirstLiteral  = 2
	base92ROMWidth      = base92WordsPerRow*base92LiteralPitch + 3
)

type base92Artifact struct {
	Words []int64
}

func packBase92(data []byte) (base92Artifact, error) {
	for _, value := range data {
		if value < 32 || value > 122 {
			return base92Artifact{}, fmt.Errorf("byte %d is outside ASCII range 32..122", value)
		}
	}

	words := make([]int64, 0, (len(data)+base92CharsPerWord-1)/base92CharsPerWord)
	for start := 0; start < len(data); start += base92CharsPerWord {
		end := min(start+base92CharsPerWord, len(data))
		var word, place int64 = 0, 1
		for _, value := range data[start:end] {
			word += int64(value-31) * place
			place *= base92Radix
		}
		digits := strconv.FormatInt(word, 10)
		if len(digits) > base92LiteralDigits {
			return base92Artifact{}, fmt.Errorf("base-92 word %d needs %d digits", word, len(digits))
		}
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			return base92Artifact{}, fmt.Errorf("base-92 word %d is not reverse-safe", word)
		}
		words = append(words, word)
	}
	return base92Artifact{Words: words}, nil
}

func unpackBase92(artifact base92Artifact) []byte {
	output := make([]byte, 0, len(artifact.Words)*base92CharsPerWord)
	for _, original := range artifact.Words {
		word := original
		for range base92CharsPerWord {
			code := word % base92Radix
			if code == 0 {
				return output
			}
			output = append(output, byte(code+31))
			word /= base92Radix
		}
	}
	return output
}

func base92ROMBlock(artifact base92Artifact) ([]byte, error) {
	rows := (len(artifact.Words) + base92WordsPerRow - 1) / base92WordsPerRow
	interior := make([]string, rows)

	for rowIndex := range rows {
		row := []byte(strings.Repeat(" ", base92ROMWidth))
		east := rowIndex%2 == 0
		last := rowIndex == rows-1
		if east {
			if rowIndex == 0 {
				row[0], row[1] = '@', '>'
			} else {
				row[0] = '>'
			}
			if !last {
				row[base92ROMWidth-1] = 'v'
			}
		} else {
			row[base92ROMWidth-1] = '<'
			if !last {
				row[0] = 'v'
			}
		}

		start := rowIndex * base92WordsPerRow
		end := min(start+base92WordsPerRow, len(artifact.Words))
		rowWords := artifact.Words[start:end]
		for logicalIndex, word := range rowWords {
			slot := logicalIndex
			if !east {
				slot = len(rowWords) - 1 - logicalIndex
			}
			left := base92FirstLiteral + slot*base92LiteralPitch
			digits := strconv.FormatInt(word, 10)
			if !east {
				digits = reverse(digits)
			}
			row[left], row[left+base92LiteralDigits+1] = '`', '`'
			copy(row[left+1:], digits)
			if east {
				row[left+base92LiteralDigits+2] = 's'
			} else {
				row[left-1] = 's'
			}
		}

		if last {
			lastSlot := len(rowWords) - 1
			if !east {
				lastSlot = 0
			}
			left := base92FirstLiteral + lastSlot*base92LiteralPitch
			if east {
				row[left+base92LiteralDigits+3] = 'H'
			} else {
				row[left-2] = 'H'
			}
		}
		interior[rowIndex] = string(row)
	}

	block := huffmanROMDefinition{
		Name:     "history_base92_rom",
		Size:     fmt.Sprintf("%dx%d", base92ROMWidth, rows),
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

func equalBase92Data(artifact base92Artifact, data []byte) bool {
	return bytes.Equal(unpackBase92(artifact), data)
}
