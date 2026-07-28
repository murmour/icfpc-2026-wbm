package main

import (
	"slices"
	"testing"
)

func TestHuffmanTableRoundTrip(t *testing.T) {
	data := historyLesson(t)
	artifact := compressHuffman(data, 1024, 36, 32)
	table, err := huffmanTable(artifact)
	if err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(unpackHuffmanTable(table), table.Codes) {
		t.Fatal("packed table does not round-trip")
	}
	if len(table.Words) != 36 {
		t.Fatalf("got %d table words, want 36", len(table.Words))
	}
	width, height := huffmanTableDimensions(table)
	if width != 50 || height != 20 {
		t.Fatalf("table dimensions %dx%d, want 50x20", width, height)
	}
}
