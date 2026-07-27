package main

import (
	"fmt"
	"strings"
)

type decoderTrie struct {
	zero   *decoderTrie
	one    *decoderTrie
	symbol *huffmanSymbol
}

func buildDecoderTrie(symbols []huffmanSymbol) (*decoderTrie, error) {
	root := &decoderTrie{}
	for index := range symbols {
		symbol := &symbols[index]
		node := root
		for _, bit := range symbol.Code {
			switch bit {
			case '0':
				if node.zero == nil {
					node.zero = &decoderTrie{}
				}
				node = node.zero
			case '1':
				if node.one == nil {
					node.one = &decoderTrie{}
				}
				node = node.one
			default:
				return nil, fmt.Errorf("invalid code bit %q", bit)
			}
			if node.symbol != nil {
				return nil, fmt.Errorf("code for symbol %d extends a leaf", symbol.ID)
			}
		}
		if node.zero != nil || node.one != nil || node.symbol != nil {
			return nil, fmt.Errorf("duplicate or prefix code for symbol %d", symbol.ID)
		}
		node.symbol = symbol
	}
	return root, nil
}

func writeIndent(output *strings.Builder, depth int) {
	output.WriteString(strings.Repeat("  ", depth))
}

func emitDecodedSymbol(
	output *strings.Builder,
	symbol *huffmanSymbol,
	bytePrograms map[byte]string,
	depth int,
) {
	var values []byte
	switch symbol.Kind {
	case "byte":
		if symbol.Byte != nil {
			values = []byte{*symbol.Byte}
		}
	case "macro":
		values = []byte(symbol.Text)
	case "eof":
		writeIndent(output, depth)
		output.WriteString("halt\n")
		return
	}
	for _, value := range values {
		writeIndent(output, depth)
		fmt.Fprintf(output, "raw %s\n", bytePrograms[value])
		writeIndent(output, depth)
		output.WriteString("send bytes\n")
	}
}

func emitDecoderNode(
	output *strings.Builder,
	node *decoderTrie,
	bytePrograms map[byte]string,
	depth int,
) {
	if node == nil {
		writeIndent(output, depth)
		output.WriteString("nop\n")
		return
	}
	if node.symbol != nil {
		emitDecodedSymbol(output, node.symbol, bytePrograms, depth)
		return
	}

	writeIndent(output, depth)
	output.WriteString("A = recv bits\n")
	writeIndent(output, depth)
	output.WriteString("if sign A {\n")
	writeIndent(output, depth+1)
	output.WriteString("negative {\n")
	writeIndent(output, depth+2)
	output.WriteString("nop\n")
	writeIndent(output, depth+1)
	output.WriteString("}\n")
	writeIndent(output, depth+1)
	output.WriteString("zero {\n")
	emitDecoderNode(output, node.zero, bytePrograms, depth+2)
	writeIndent(output, depth+1)
	output.WriteString("}\n")
	writeIndent(output, depth+1)
	output.WriteString("positive {\n")
	emitDecoderNode(output, node.one, bytePrograms, depth+2)
	writeIndent(output, depth+1)
	output.WriteString("}\n")
	writeIndent(output, depth)
	output.WriteString("}\n")
}

func huffmanDecoderSource(artifact huffmanArtifact) (string, error) {
	root, err := buildDecoderTrie(artifact.Symbols)
	if err != nil {
		return "", err
	}
	needed := make(map[byte]bool)
	for _, symbol := range artifact.Symbols {
		switch symbol.Kind {
		case "byte":
			if symbol.Byte != nil {
				needed[*symbol.Byte] = true
			}
		case "macro":
			for _, value := range []byte(symbol.Text) {
				needed[value] = true
			}
		}
	}
	bytePrograms := shortestBytePrograms(needed)
	var output strings.Builder
	output.WriteString("block history_huffman_decoder\n\n")
	output.WriteString("input bits auto\n")
	output.WriteString("output bytes auto\n\n")
	output.WriteString("forever {\n")
	emitDecoderNode(&output, root, bytePrograms, 1)
	output.WriteString("}\n")
	return output.String(), nil
}
