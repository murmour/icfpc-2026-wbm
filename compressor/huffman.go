package main

import (
	"bytes"
	"fmt"
	"sort"
	"strings"
)

const huffmanWordBits = 63

type huffmanSymbol struct {
	ID        int    `json:"id"`
	Kind      string `json:"kind"`
	Text      string `json:"text,omitempty"`
	Byte      *byte  `json:"byte,omitempty"`
	Frequency int    `json:"frequency"`
	BitLength int    `json:"bit_length"`
	Code      string `json:"code"`
}

type huffmanArtifact struct {
	Version            int             `json:"version"`
	SourceLength       int             `json:"source_length"`
	TokenCount         int             `json:"token_count"`
	MacroCount         int             `json:"macro_count"`
	DictionaryBytes    int             `json:"dictionary_bytes"`
	BitLength          int             `json:"bit_length"`
	RepresentationBits int             `json:"representation_bits"`
	WordBits           int             `json:"word_bits"`
	Words              []uint64        `json:"words"`
	Symbols            []huffmanSymbol `json:"symbols"`
}

type huffmanNode struct {
	weight    int
	minSymbol int
	symbol    int
	left      *huffmanNode
	right     *huffmanNode
}

type phraseCandidate struct {
	text  string
	count int
	score int
}

type tokenizationResult struct {
	tokens    []int
	lengths   map[int]int
	bitLength int
}

func minePhraseCandidates(data []byte, limit, maxLength int) []string {
	const (
		minLength = 2
		minCount  = 3
	)
	counts := make(map[string]int)
	for length := minLength; length <= maxLength; length++ {
		for start := 0; start+length <= len(data); start++ {
			counts[string(data[start:start+length])]++
		}
	}

	var candidates []phraseCandidate
	for text, count := range counts {
		if count < minCount {
			continue
		}
		candidates = append(candidates, phraseCandidate{
			text:  text,
			count: count,
			score: (len(text) - 1) * (count - 1),
		})
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].score != candidates[j].score {
			return candidates[i].score > candidates[j].score
		}
		if len(candidates[i].text) != len(candidates[j].text) {
			return len(candidates[i].text) > len(candidates[j].text)
		}
		return candidates[i].text < candidates[j].text
	})
	if len(candidates) > limit {
		candidates = candidates[:limit]
	}

	result := make([]string, len(candidates))
	for index, candidate := range candidates {
		result[index] = candidate.text
	}
	return result
}

func tokenizeWithCosts(data []byte, phrases []string, costs map[int]int) []int {
	const unreachable = int(^uint(0) >> 2)
	size := len(data)
	best := make([]int, size+1)
	choiceID := make([]int, size)
	choiceLength := make([]int, size)
	for index := 0; index < size; index++ {
		best[index] = unreachable
	}
	best[size] = 0

	for index := size - 1; index >= 0; index-- {
		rawID := int(data[index])
		rawCost := costs[rawID]
		if rawCost == 0 {
			rawCost = 8
		}
		best[index] = rawCost + best[index+1]
		choiceID[index] = rawID
		choiceLength[index] = 1

		for phraseIndex, phrase := range phrases {
			if index+len(phrase) > size || !bytes.Equal(data[index:index+len(phrase)], []byte(phrase)) {
				continue
			}
			id := 256 + phraseIndex
			cost := costs[id]
			if cost == 0 {
				cost = 7
			}
			total := cost + best[index+len(phrase)]
			if total < best[index] ||
				(total == best[index] && len(phrase) > choiceLength[index]) {
				best[index] = total
				choiceID[index] = id
				choiceLength[index] = len(phrase)
			}
		}
	}

	tokens := make([]int, 0, size)
	for index := 0; index < size; {
		tokens = append(tokens, choiceID[index])
		index += choiceLength[index]
	}
	return tokens
}

func huffmanLengths(frequencies map[int]int) map[int]int {
	nodes := make([]*huffmanNode, 0, len(frequencies))
	for symbol, frequency := range frequencies {
		if frequency == 0 {
			continue
		}
		nodes = append(nodes, &huffmanNode{
			weight:    frequency,
			minSymbol: symbol,
			symbol:    symbol,
		})
	}
	if len(nodes) == 1 {
		return map[int]int{nodes[0].symbol: 1}
	}

	less := func(first, second *huffmanNode) bool {
		if first.weight != second.weight {
			return first.weight < second.weight
		}
		return first.minSymbol < second.minSymbol
	}
	for len(nodes) > 1 {
		sort.Slice(nodes, func(i, j int) bool { return less(nodes[i], nodes[j]) })
		first, second := nodes[0], nodes[1]
		nodes = append(nodes[2:], &huffmanNode{
			weight:    first.weight + second.weight,
			minSymbol: min(first.minSymbol, second.minSymbol),
			symbol:    -1,
			left:      first,
			right:     second,
		})
	}

	lengths := make(map[int]int)
	var walk func(*huffmanNode, int)
	walk = func(node *huffmanNode, depth int) {
		if node.symbol >= 0 {
			lengths[node.symbol] = depth
			return
		}
		walk(node.left, depth+1)
		walk(node.right, depth+1)
	}
	walk(nodes[0], 0)
	return lengths
}

func optimizeTokenization(data []byte, phrases []string) tokenizationResult {
	costs := make(map[int]int)
	for _, value := range data {
		costs[int(value)] = 8
	}
	for index := range phrases {
		costs[256+index] = 7
	}

	eofID := 256 + len(phrases)
	var bestResult tokenizationResult
	previousKey := ""
	for iteration := 0; iteration < 32; iteration++ {
		tokens := tokenizeWithCosts(data, phrases, costs)
		frequencies := make(map[int]int)
		for _, token := range tokens {
			frequencies[token]++
		}
		frequencies[eofID] = 1
		lengths := huffmanLengths(frequencies)

		bitLength := lengths[eofID]
		for _, token := range tokens {
			bitLength += lengths[token]
		}
		if bestResult.tokens == nil || bitLength < bestResult.bitLength {
			bestResult = tokenizationResult{
				tokens:    append([]int(nil), tokens...),
				lengths:   lengths,
				bitLength: bitLength,
			}
		}

		var key strings.Builder
		for _, token := range tokens {
			fmt.Fprintf(&key, "%d,", token)
		}
		if key.String() == previousKey {
			break
		}
		previousKey = key.String()

		for symbol, length := range lengths {
			costs[symbol] = length
		}
		for symbol := range costs {
			if _, used := lengths[symbol]; !used {
				costs[symbol] = 64
			}
		}
	}
	return bestResult
}

func dictionaryBytes(phrases []string) int {
	total := 0
	for _, phrase := range phrases {
		total += len(phrase)
	}
	return total
}

func selectPhrases(
	data []byte,
	candidateLimit, macroLimit, maxMacroLength int,
) ([]string, tokenizationResult) {
	candidates := minePhraseCandidates(data, candidateLimit, maxMacroLength)
	selected := make([]string, 0, macroLimit)
	best := optimizeTokenization(data, selected)
	bestRepresentation := best.bitLength

	for _, candidate := range candidates {
		if len(selected) >= macroLimit {
			break
		}
		trialPhrases := append(append([]string(nil), selected...), candidate)
		trial := optimizeTokenization(data, trialPhrases)
		trialRepresentation := trial.bitLength + 8*dictionaryBytes(trialPhrases)
		if trialRepresentation < bestRepresentation {
			selected = trialPhrases
			best = trial
			bestRepresentation = trialRepresentation
		}
	}
	return selected, best
}

func canonicalCodes(lengths map[int]int, salt uint64) map[int]uint64 {
	symbols := make([]int, 0, len(lengths))
	for symbol := range lengths {
		symbols = append(symbols, symbol)
	}
	sort.Slice(symbols, func(i, j int) bool {
		if lengths[symbols[i]] != lengths[symbols[j]] {
			return lengths[symbols[i]] < lengths[symbols[j]]
		}
		if salt == 0 {
			return symbols[i] < symbols[j]
		}
		return canonicalTieKey(symbols[i], salt) < canonicalTieKey(symbols[j], salt)
	})

	codes := make(map[int]uint64)
	var code uint64
	previousLength := 0
	for _, symbol := range symbols {
		length := lengths[symbol]
		code <<= length - previousLength
		codes[symbol] = code
		code++
		previousLength = length
	}
	return codes
}

func canonicalTieKey(symbol int, salt uint64) uint64 {
	value := uint64(symbol) + salt*0x9e3779b97f4a7c15
	value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9
	value = (value ^ (value >> 27)) * 0x94d049bb133111eb
	return value ^ (value >> 31)
}

func codeString(code uint64, length int) string {
	var result strings.Builder
	for bit := length - 1; bit >= 0; bit-- {
		if code&(uint64(1)<<bit) != 0 {
			result.WriteByte('1')
		} else {
			result.WriteByte('0')
		}
	}
	return result.String()
}

func compressHuffman(
	data []byte,
	candidateLimit, macroLimit, maxMacroLength int,
) huffmanArtifact {
	phrases, result := selectPhrases(data, candidateLimit, macroLimit, maxMacroLength)
	eofID := 256 + len(phrases)

	frequencies := make(map[int]int)
	for _, token := range result.tokens {
		frequencies[token]++
	}
	frequencies[eofID] = 1

	stream := append(append([]int(nil), result.tokens...), eofID)
	codes := canonicalCodes(result.lengths, 311913)
	words, bitLength := packHuffmanWords(stream, result.lengths, codes)
	symbols := buildHuffmanSymbols(result.lengths, codes, frequencies, eofID, phrases)

	dictionarySize := dictionaryBytes(phrases)
	return huffmanArtifact{
		Version:            1,
		SourceLength:       len(data),
		TokenCount:         len(result.tokens),
		MacroCount:         len(phrases),
		DictionaryBytes:    dictionarySize,
		BitLength:          bitLength,
		RepresentationBits: bitLength + 8*dictionarySize,
		WordBits:           huffmanWordBits,
		Words:              words,
		Symbols:            symbols,
	}
}

func buildHuffmanSymbols(
	lengths map[int]int,
	codes map[int]uint64,
	frequencies map[int]int,
	eofID int,
	phrases []string,
) []huffmanSymbol {
	var symbols []huffmanSymbol
	for symbol, length := range lengths {
		entry := huffmanSymbol{
			ID:        symbol,
			Frequency: frequencies[symbol],
			BitLength: length,
			Code:      codeString(codes[symbol], length),
		}
		switch {
		case symbol < 256:
			value := byte(symbol)
			entry.Kind = "byte"
			entry.Byte = &value
		case symbol == eofID:
			entry.Kind = "eof"
		default:
			entry.Kind = "macro"
			entry.Text = phrases[symbol-256]
		}
		symbols = append(symbols, entry)
	}
	sort.Slice(symbols, func(i, j int) bool { return symbols[i].ID < symbols[j].ID })
	return symbols
}

func packHuffmanWords(stream []int, lengths map[int]int, codes map[int]uint64) ([]uint64, int) {
	var words []uint64
	var word uint64
	bitOffset := 0
	bitLength := 0
	for _, token := range stream {
		code := codes[token]
		length := lengths[token]
		for bit := length - 1; bit >= 0; bit-- {
			if code&(uint64(1)<<bit) != 0 {
				word |= uint64(1) << bitOffset
			}
			bitOffset++
			bitLength++
			if bitOffset == huffmanWordBits {
				words = append(words, word)
				word, bitOffset = 0, 0
			}
		}
	}
	if bitOffset != 0 {
		words = append(words, word)
	}
	return words, bitLength
}

func decompressHuffman(artifact huffmanArtifact) ([]byte, error) {
	byCode := make(map[string]huffmanSymbol)
	for _, symbol := range artifact.Symbols {
		byCode[symbol.Code] = symbol
	}

	var output []byte
	var prefix strings.Builder
	for bitIndex := 0; bitIndex < artifact.BitLength; bitIndex++ {
		word := artifact.Words[bitIndex/artifact.WordBits]
		if word&(uint64(1)<<uint(bitIndex%artifact.WordBits)) != 0 {
			prefix.WriteByte('1')
		} else {
			prefix.WriteByte('0')
		}
		symbol, found := byCode[prefix.String()]
		if !found {
			continue
		}
		switch symbol.Kind {
		case "byte":
			if symbol.Byte == nil {
				return nil, fmt.Errorf("byte symbol %d has no value", symbol.ID)
			}
			output = append(output, *symbol.Byte)
		case "macro":
			output = append(output, symbol.Text...)
		case "eof":
			return output, nil
		default:
			return nil, fmt.Errorf("unknown symbol kind %q", symbol.Kind)
		}
		prefix.Reset()
	}
	return nil, fmt.Errorf("compressed stream ended without EOF")
}
