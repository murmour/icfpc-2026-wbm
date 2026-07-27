package main

import (
	"os"
	"strconv"
	"testing"
)

func TestBase71HistoryRoundTrip(t *testing.T) {
	input, err := os.ReadFile("../../../problems/history_lesson.txt")
	if err != nil {
		t.Fatal(err)
	}
	artifact, err := packBase71(input)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(artifact.Alphabet), 71; got != want {
		t.Fatalf("alphabet size = %d, want %d", got, want)
	}
	if got, want := len(artifact.Words), 281; got != want {
		t.Fatalf("word count = %d, want %d", got, want)
	}
	if !equalBase71Data(artifact, input) {
		t.Fatal("base-71 data did not round-trip")
	}
	for index, word := range artifact.Words {
		digits := strconv.FormatInt(word, 10)
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			t.Fatalf("word %d is not reverse-safe: %d", index, word)
		}
	}
}
