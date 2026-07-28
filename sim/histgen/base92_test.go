package main

import (
	"strconv"
	"testing"
)

func TestBase92HistoryRoundTrip(t *testing.T) {
	input := historyLesson(t)
	artifact, err := packBase92(input)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(artifact.Words), 313; got != want {
		t.Fatalf("word count = %d, want %d", got, want)
	}
	if !equalBase92Data(artifact, input) {
		t.Fatal("base-92 data did not round-trip")
	}
	for index, word := range artifact.Words {
		digits := strconv.FormatInt(word, 10)
		if len(digits) > base92LiteralDigits {
			t.Fatalf("word %d has %d digits", index, len(digits))
		}
		if _, err := strconv.ParseInt(reverse(digits), 10, 64); err != nil {
			t.Fatalf("word %d is not reverse-safe: %d", index, word)
		}
	}
}
