package main

import (
	"os"
	"slices"
	"strconv"
	"testing"
)

func TestBase99HistoryRoundTrip(t *testing.T) {
	input, err := os.ReadFile("../../../problems/history_lesson.txt")
	if err != nil {
		t.Fatal(err)
	}
	artifact, err := packBase99(input)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(artifact.Pairs), 24; got != want {
		t.Fatalf("pair count = %d, want %d", got, want)
	}
	if got, want := len(artifact.Tokens), 2112; got != want {
		t.Fatalf("token count = %d, want %d", got, want)
	}
	if got, want := len(artifact.Words), 264; got != want {
		t.Fatalf("word count = %d, want %d", got, want)
	}
	if !slices.Contains(artifact.Tokens, base99ThirdPhraseCode) ||
		!slices.Contains(artifact.Tokens, base99SecondPhraseCode) {
		t.Fatal("packed stream did not use both compact phrase codes")
	}
	if !equalBase99Data(artifact, input) {
		t.Fatal("base-99 data did not round-trip")
	}
	var unpackedTokens []int64
	for index, word := range artifact.Words {
		digits := strconv.FormatInt(word, 10)
		if len(digits) > base99LiteralDigits {
			t.Fatalf("word %d has %d digits", index, len(digits))
		}
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			t.Fatalf("word %d is not reverse-safe: %d", index, word)
		}
		for word > 0 {
			unpackedTokens = append(unpackedTokens, word%base99Radix)
			word /= base99Radix
		}
	}
	if !slices.Equal(unpackedTokens, artifact.Tokens) {
		t.Fatal("quotient-terminated unpacking changed the token stream")
	}
}

func TestBase99PairTableFits(t *testing.T) {
	input, err := os.ReadFile("../../../problems/history_lesson.txt")
	if err != nil {
		t.Fatal(err)
	}
	artifact, err := packBase99(input)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := base99PairTableBlock(artifact); err != nil {
		t.Fatal(err)
	}
}
