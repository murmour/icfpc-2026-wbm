package main

import (
	"encoding/json"
	"strconv"
	"strings"
	"testing"
)

func TestHuffmanRoundTrip(t *testing.T) {
	input := []byte("alpha, beta, alpha, beta; alpha and beta")
	artifact := compressHuffman(input, 64, 16, 32)

	encoded, err := json.Marshal(artifact)
	if err != nil {
		t.Fatalf("marshal artifact: %v", err)
	}
	var decodedArtifact huffmanArtifact
	if err := json.Unmarshal(encoded, &decodedArtifact); err != nil {
		t.Fatalf("unmarshal artifact: %v", err)
	}
	output, err := decompressHuffman(decodedArtifact)
	if err != nil {
		t.Fatalf("decompress artifact: %v", err)
	}
	if string(output) != string(input) {
		t.Fatalf("round trip = %q, want %q", output, input)
	}

	for _, word := range artifact.Words {
		if huffmanWordBits < 64 && word >= uint64(1)<<huffmanWordBits {
			t.Fatalf("word %d does not fit in %d bits", word, huffmanWordBits)
		}
	}
}

func TestCanonicalCodesArePrefixFree(t *testing.T) {
	artifact := compressHuffman(
		[]byte("the quick brown fox jumps over the lazy dog"),
		32,
		8,
		32,
	)
	for firstIndex, first := range artifact.Symbols {
		for secondIndex, second := range artifact.Symbols {
			if firstIndex == secondIndex {
				continue
			}
			if strings.HasPrefix(second.Code, first.Code) {
				t.Fatalf("code %q for symbol %d prefixes code %q for symbol %d",
					first.Code, first.ID, second.Code, second.ID)
			}
		}
	}
}

func TestHistoryArtifact(t *testing.T) {
	input := historyLesson(t)
	artifact := compressHuffman(input, 1024, 36, 32)
	output, err := decompressHuffman(artifact)
	if err != nil {
		t.Fatalf("decompress artifact: %v", err)
	}
	if string(output) != string(input) {
		t.Fatal("generated artifact does not reproduce History Lesson")
	}
	if artifact.BitLength > 12_500 {
		t.Fatalf("compressed stream grew to %d bits", artifact.BitLength)
	}
}

func TestHuffmanROMLiteralsFitSignedRegisterInBothDirections(t *testing.T) {
	input := historyLesson(t)
	artifact := compressHuffman(input, 1024, 36, 32)
	if !huffmanROMWordsFitFixed(artifact.Words) {
		t.Fatal("selected canonical ordering does not fit the compact Huffman ROM")
	}

	for _, word := range artifact.Words {
		digits := strconv.FormatUint(word, 10)
		for _, spelling := range []string{digits, reverse(digits)} {
			if _, err := strconv.ParseInt(spelling, 10, 64); err != nil {
				t.Fatalf("word %d has invalid spelling %q: %v", word, spelling, err)
			}
		}
	}

	table, err := huffmanTable(artifact)
	if err != nil {
		t.Fatalf("build table: %v", err)
	}
	for _, word := range table.Words {
		digits := strconv.FormatInt(word, 10)
		for _, spelling := range []string{digits, reverse(digits)} {
			if _, err := strconv.ParseInt(spelling, 10, 64); err != nil {
				t.Fatalf("table word %d has invalid spelling %q: %v", word, spelling, err)
			}
		}
	}
}
