package main

import (
	"strconv"
	"testing"
)

func TestBase75HistoryRoundTrip(t *testing.T) {
	input := historyLesson(t)
	artifact, err := packBase75(input)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(artifact.Words), 296; got != want {
		t.Fatalf("word count = %d, want %d", got, want)
	}
	if !equalBase75Data(artifact, input) {
		t.Fatal("base-75 data did not round-trip")
	}
	for index, word := range artifact.Words {
		digits := strconv.FormatInt(word, 10)
		if len(digits) > base75LiteralDigits {
			t.Fatalf("word %d has %d digits", index, len(digits))
		}
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			t.Fatalf("word %d is not reverse-safe: %d", index, word)
		}
	}
}
