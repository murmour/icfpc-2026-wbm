package main

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

const (
	huffmanROMWordsPerRow  = 3
	huffmanROMLiteralPitch = 22
)

type huffmanROMPort struct {
	Type        string `json:"type"`
	Side        string `json:"side"`
	OffsetRange []int  `json:"offset_range"`
	LengthRange []int  `json:"length_range"`
}

type huffmanROMDefinition struct {
	Name     string                    `json:"name"`
	Size     string                    `json:"size"`
	Interior []string                  `json:"interior"`
	Ports    map[string]huffmanROMPort `json:"ports"`
}

func huffmanROMWordsFitFixed(words []uint64) bool {
	for _, word := range words {
		digits := strconv.FormatUint(word, 10)
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			return false
		}
		if len(digits)+3 > huffmanROMLiteralPitch {
			return false
		}
	}
	return true
}

func huffmanROMBlock(artifact huffmanArtifact) ([]byte, error) {
	rows := (len(artifact.Words) + huffmanROMWordsPerRow - 1) / huffmanROMWordsPerRow
	width := huffmanROMWordsPerRow*huffmanROMLiteralPitch + 3
	interior := make([]string, rows)

	for rowIndex := 0; rowIndex < rows; rowIndex++ {
		row := []byte(strings.Repeat(" ", width))
		east := rowIndex%2 == 0
		last := rowIndex == rows-1
		if east {
			if rowIndex == 0 {
				row[0] = '@'
			} else {
				row[0] = '>'
			}
			if !last {
				row[width-1] = 'v'
			}
		} else {
			row[width-1] = '<'
			if !last {
				row[0] = 'v'
			}
		}

		start := rowIndex * huffmanROMWordsPerRow
		end := min(start+huffmanROMWordsPerRow, len(artifact.Words))
		rowWords := artifact.Words[start:end]
		firstLiteral := 3
		if east {
			firstLiteral = 1
		}
		for logicalIndex, word := range rowWords {
			slot := logicalIndex
			if !east {
				slot = len(rowWords) - 1 - logicalIndex
			}
			left := firstLiteral + slot*huffmanROMLiteralPitch
			digits := strconv.FormatUint(word, 10)
			if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
				return nil, fmt.Errorf("Huffman word %d is invalid in reverse: %w", word, err)
			}
			if !east {
				digits = reverse(digits)
			}
			row[left], row[left+huffmanROMLiteralPitch-2] = '`', '`'
			copy(row[left+1:], digits)
			if east {
				row[left+huffmanROMLiteralPitch-1] = 's'
			} else {
				row[left-1] = 's'
			}
		}

		if last {
			lastSlot := len(rowWords) - 1
			if !east {
				lastSlot = 0
			}
			left := firstLiteral + lastSlot*huffmanROMLiteralPitch
			if east {
				row[left+huffmanROMLiteralPitch] = 'H'
			} else {
				row[left-2] = 'H'
			}
		}
		interior[rowIndex] = string(row)
	}

	block := huffmanROMDefinition{
		Name:     "history_huffman_rom",
		Size:     fmt.Sprintf("%dx%d", width, rows),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"words": {
				Type:        "output",
				Side:        "right",
				OffsetRange: []int{2, 2},
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
