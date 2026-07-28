package main

import (
	"os"
	"testing"
)

func historyLesson(t *testing.T) []byte {
	t.Helper()
	data, err := os.ReadFile("../../public_tests/history_lesson.txt")
	if err != nil {
		t.Fatal(err)
	}
	if len(data) == 0 {
		t.Fatal("history lesson fixture is empty")
	}
	return data
}
