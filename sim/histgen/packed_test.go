package main

import (
	"bytes"
	"os"
	"strconv"
	"testing"
)

func unpackASCII(words []packedWord) []byte {
	var output []byte
	for _, word := range words {
		value := word.value
		for range packedCharsPerWord - 1 {
			output = append(output, byte(value&0x7f))
			value >>= 7
		}
		switch value {
		case packedPaddingByte:
		case packedEOFByte:
			return output
		default:
			output = append(output, byte(value))
		}
	}
	return output
}

func TestPackASCIIHistoryRoundTrip(t *testing.T) {
	input, err := os.ReadFile("../../../problems/history_lesson.txt")
	if err != nil {
		t.Fatal(err)
	}

	words := packASCII(input)
	if got, want := len(words), 315; got != want {
		t.Fatalf("packed word count = %d, want %d", got, want)
	}
	if output := unpackASCII(words); !bytes.Equal(output, input) {
		t.Fatal("packed history did not round-trip")
	}

	for index, word := range words {
		digits := strconv.FormatInt(word.value, 10)
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			t.Fatalf("word %d is not safe in reverse: %d", index, word.value)
		}
	}
}

func TestPackASCIIEndsWithEOF(t *testing.T) {
	input := bytes.Repeat([]byte("abcdefgh"), 4)
	words := packASCII(input)
	lastControl := byte(words[len(words)-1].value >> (7 * (packedCharsPerWord - 1)))
	if lastControl != packedEOFByte {
		t.Fatalf("final control = %d, want EOF %d", lastControl, packedEOFByte)
	}
}
