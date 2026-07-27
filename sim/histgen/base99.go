package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

const (
	base99Radix            = int64(99)
	base99CodesPerWord     = 8
	base99WordsPerRow      = 4
	base99LiteralDigits    = 16
	base99LiteralPitch     = base99LiteralDigits + 3
	base99FirstLiteral     = 2
	base99ROMWidth         = base99WordsPerRow*base99LiteralPitch + 3
	base99ThirdPhraseCode  = int64(0)
	base99SecondPhraseCode = int64(17)
	base99PhraseCode       = int64(74)
	base99PairFirstCode    = int64(75)
	base99PairCount        = 24
	base99PairRadix        = int64(74)
	base99TableWidth       = 47
	base99TableRows        = 4
	base99TableFloorX      = 6
	base99ASCIIFloorX      = 1
)

var base99Phrase = []byte(" and ")
var base99SecondPhrase = []byte(", US")
var base99ThirdPhrase = []byte("the")
var base99LastRowShifts = []int{-1, 0, 0, 0}

type base99Pair struct {
	Code  int64
	Left  int64
	Right int64
}

type base99Artifact struct {
	Words  []int64
	Tokens []int64
	Pairs  []base99Pair
}

type bytePair struct {
	Left  byte
	Right byte
}

func base99LiteralCodes() map[byte]int64 {
	codes := make(map[byte]int64)
	for value := 0; value <= 255; value++ {
		if code, found := base75Code(byte(value)); found {
			codes[byte(value)] = code
		}
	}
	delete(codes, 'q')
	return codes
}

func marshalBase99Block(value any) ([]byte, error) {
	var output bytes.Buffer
	encoder := json.NewEncoder(&output)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return output.Bytes(), nil
}

func base99PairScore(data []byte, selected map[bytePair]bool) int {
	dp := make([]int, len(data)+1)
	for index := len(data) - 1; index >= 0; index-- {
		dp[index] = 1 + dp[index+1]
		if index+1 < len(data) &&
			selected[bytePair{Left: data[index], Right: data[index+1]}] &&
			1+dp[index+2] < dp[index] {
			dp[index] = 1 + dp[index+2]
		}
		if index+len(base99Phrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99Phrase)], base99Phrase) &&
			1+dp[index+len(base99Phrase)] < dp[index] {
			dp[index] = 1 + dp[index+len(base99Phrase)]
		}
		if index+len(base99SecondPhrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99SecondPhrase)], base99SecondPhrase) &&
			1+dp[index+len(base99SecondPhrase)] < dp[index] {
			dp[index] = 1 + dp[index+len(base99SecondPhrase)]
		}
		if index+len(base99ThirdPhrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99ThirdPhrase)], base99ThirdPhrase) &&
			1+dp[index+len(base99ThirdPhrase)] < dp[index] {
			dp[index] = 1 + dp[index+len(base99ThirdPhrase)]
		}
	}
	return dp[0]
}

func chooseBase99Pairs(data []byte) ([]bytePair, error) {
	literalCodes := base99LiteralCodes()
	candidateSet := make(map[bytePair]bool)
	for index := 0; index+1 < len(data); index++ {
		if _, found := literalCodes[data[index]]; !found {
			return nil, fmt.Errorf("byte %d is outside the base-99 alphabet", data[index])
		}
		if _, found := literalCodes[data[index+1]]; !found {
			return nil, fmt.Errorf("byte %d is outside the base-99 alphabet", data[index+1])
		}
		candidateSet[bytePair{Left: data[index], Right: data[index+1]}] = true
	}
	candidates := make([]bytePair, 0, len(candidateSet))
	for candidate := range candidateSet {
		candidates = append(candidates, candidate)
	}

	selected := make(map[bytePair]bool)
	pairs := make([]bytePair, 0, base99PairCount)
	for range base99PairCount {
		bestScore := len(data) + 1
		var best bytePair
		found := false
		for _, candidate := range candidates {
			if selected[candidate] {
				continue
			}
			selected[candidate] = true
			score := base99PairScore(data, selected)
			delete(selected, candidate)
			if !found || score < bestScore ||
				(score == bestScore &&
					(candidate.Left < best.Left ||
						(candidate.Left == best.Left && candidate.Right < best.Right))) {
				found = true
				bestScore = score
				best = candidate
			}
		}
		if !found {
			return nil, fmt.Errorf("only found %d usable byte pairs", len(pairs))
		}
		selected[best] = true
		pairs = append(pairs, best)
	}

	sort.Slice(pairs, func(left, right int) bool {
		leftCode := literalCodes[pairs[left].Left] +
			base99PairRadix*literalCodes[pairs[left].Right]
		rightCode := literalCodes[pairs[right].Left] +
			base99PairRadix*literalCodes[pairs[right].Right]
		return leftCode < rightCode
	})
	return pairs, nil
}

func tokenizeBase99(data []byte, pairs []bytePair) ([]int64, []base99Pair, error) {
	literalCodes := base99LiteralCodes()
	macroCodes := make(map[bytePair]int64, len(pairs))
	rules := make([]base99Pair, len(pairs))
	for index, pair := range pairs {
		code := base99PairFirstCode + int64(index)
		macroCodes[pair] = code
		rules[index] = base99Pair{
			Code:  code,
			Left:  literalCodes[pair.Left],
			Right: literalCodes[pair.Right],
		}
	}

	dp := make([]int, len(data)+1)
	for index := len(data) - 1; index >= 0; index-- {
		dp[index] = 1 + dp[index+1]
		if index+1 < len(data) {
			if _, found := macroCodes[bytePair{data[index], data[index+1]}]; found &&
				1+dp[index+2] < dp[index] {
				dp[index] = 1 + dp[index+2]
			}
		}
		if index+len(base99Phrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99Phrase)], base99Phrase) &&
			1+dp[index+len(base99Phrase)] < dp[index] {
			dp[index] = 1 + dp[index+len(base99Phrase)]
		}
		if index+len(base99SecondPhrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99SecondPhrase)], base99SecondPhrase) &&
			1+dp[index+len(base99SecondPhrase)] < dp[index] {
			dp[index] = 1 + dp[index+len(base99SecondPhrase)]
		}
		if index+len(base99ThirdPhrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99ThirdPhrase)], base99ThirdPhrase) &&
			1+dp[index+len(base99ThirdPhrase)] < dp[index] {
			dp[index] = 1 + dp[index+len(base99ThirdPhrase)]
		}
	}

	tokens := make([]int64, 0, dp[0])
	for index := 0; index < len(data); {
		if index+len(base99ThirdPhrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99ThirdPhrase)], base99ThirdPhrase) &&
			dp[index] == 1+dp[index+len(base99ThirdPhrase)] {
			tokens = append(tokens, base99ThirdPhraseCode)
			index += len(base99ThirdPhrase)
			continue
		}
		if index+len(base99SecondPhrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99SecondPhrase)], base99SecondPhrase) &&
			dp[index] == 1+dp[index+len(base99SecondPhrase)] {
			tokens = append(tokens, base99SecondPhraseCode)
			index += len(base99SecondPhrase)
			continue
		}
		if index+len(base99Phrase) <= len(data) &&
			bytes.Equal(data[index:index+len(base99Phrase)], base99Phrase) &&
			dp[index] == 1+dp[index+len(base99Phrase)] {
			tokens = append(tokens, base99PhraseCode)
			index += len(base99Phrase)
			continue
		}
		if index+1 < len(data) {
			if code, found := macroCodes[bytePair{data[index], data[index+1]}]; found &&
				dp[index] == 1+dp[index+2] {
				tokens = append(tokens, code)
				index += 2
				continue
			}
		}
		code, found := literalCodes[data[index]]
		if !found {
			return nil, nil, fmt.Errorf("byte %d is outside the base-99 alphabet", data[index])
		}
		tokens = append(tokens, code)
		index++
	}
	return tokens, rules, nil
}

func packBase99(data []byte) (base99Artifact, error) {
	pairs, err := chooseBase99Pairs(data)
	if err != nil {
		return base99Artifact{}, err
	}
	tokens, rules, err := tokenizeBase99(data, pairs)
	if err != nil {
		return base99Artifact{}, err
	}

	const maximumWord = int64(9_999_999_999_999_999)
	const maximumCodesPerWord = 9
	cost := make([]int, len(tokens)+1)
	lengths := make([]int, len(tokens))
	for start := len(tokens) - 1; start >= 0; start-- {
		cost[start] = len(tokens) + 1
		var word, place int64 = 0, 1
		for length := 1; length <= maximumCodesPerWord && start+length <= len(tokens); length++ {
			code := tokens[start+length-1]
			word += code * place
			if word > maximumWord {
				break
			}
			if code == 0 {
				place *= base99Radix
				continue
			}
			candidate := 1 + cost[start+length]
			if candidate < cost[start] ||
				(candidate == cost[start] && length > lengths[start]) {
				cost[start], lengths[start] = candidate, length
			}
			place *= base99Radix
		}
		if lengths[start] == 0 {
			return base99Artifact{}, fmt.Errorf("cannot pack base-99 token at %d", start)
		}
	}

	words := make([]int64, 0, cost[0])
	for start := 0; start < len(tokens); start += lengths[start] {
		var word, place int64 = 0, 1
		for _, code := range tokens[start : start+lengths[start]] {
			word += code * place
			place *= base99Radix
		}
		words = append(words, word)
	}
	return base99Artifact{Words: words, Tokens: tokens, Pairs: rules}, nil
}

func unpackBase99(artifact base99Artifact) ([]byte, error) {
	rules := make(map[int64]base99Pair, len(artifact.Pairs))
	for _, pair := range artifact.Pairs {
		rules[pair.Code] = pair
	}

	output := make([]byte, 0, len(artifact.Tokens)*2)
	for _, token := range artifact.Tokens {
		if token == base99ThirdPhraseCode {
			output = append(output, base99ThirdPhrase...)
			continue
		}
		if token == base99SecondPhraseCode {
			output = append(output, base99SecondPhrase...)
			continue
		}
		if token <= base99PhraseCode {
			value, found := base75Byte(token)
			if !found {
				return nil, fmt.Errorf("unknown base-99 literal %d", token)
			}
			output = append(output, value...)
			continue
		}
		pair, found := rules[token]
		if !found {
			return nil, fmt.Errorf("unknown base-99 token %d", token)
		}
		left, leftFound := base75Byte(pair.Left)
		right, rightFound := base75Byte(pair.Right)
		if !leftFound || !rightFound || len(left) != 1 || len(right) != 1 {
			return nil, fmt.Errorf("invalid base-99 pair %d", token)
		}
		output = append(output, left[0], right[0])
	}
	return output, nil
}

func base99ROMBlock(artifact base99Artifact) ([]byte, error) {
	rows := (len(artifact.Words) + base99WordsPerRow - 1) / base99WordsPerRow
	interior := make([]string, rows)
	for rowIndex := range rows {
		row := []byte(strings.Repeat(" ", base99ROMWidth))
		east := rowIndex%2 == 0
		last := rowIndex == rows-1
		if east {
			if rowIndex == 0 {
				row[0], row[1] = '@', '>'
			} else {
				row[0] = '>'
			}
			if !last {
				row[base99ROMWidth-1] = 'v'
			}
		} else {
			row[base99ROMWidth-1] = '<'
			if !last {
				row[0] = 'v'
			}
		}

		start := rowIndex * base99WordsPerRow
		end := min(start+base99WordsPerRow, len(artifact.Words))
		rowWords := artifact.Words[start:end]
		for logicalIndex, word := range rowWords {
			slot := logicalIndex
			if !east {
				slot = len(rowWords) - 1 - logicalIndex
			}
			left := base99FirstLiteral + slot*base99LiteralPitch
			if last && east {
				left += base99LastRowShifts[slot]
			}
			digits := strconv.FormatInt(word, 10)
			if !east {
				digits = reverse(digits)
			}
			row[left], row[left+base99LiteralDigits+1] = '`', '`'
			copy(row[left+1:], digits)
			if east {
				row[left+base99LiteralDigits+2] = 's'
			} else {
				row[left-1] = 's'
			}
		}

		if last {
			lastSlot := len(rowWords) - 1
			if !east {
				lastSlot = 0
			}
			left := base99FirstLiteral + lastSlot*base99LiteralPitch
			if east {
				left += base99LastRowShifts[lastSlot]
			}
			if east {
				row[left+base99LiteralDigits+3] = 'H'
			} else {
				row[left-2] = 'H'
			}
		}
		interior[rowIndex] = string(row)
	}

	block := huffmanROMDefinition{
		Name:     "history_base99_rom",
		Size:     fmt.Sprintf("%dx%d", base99ROMWidth, rows),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"words": {
				Type:        "output",
				Side:        "bottom",
				OffsetRange: []int{57, 57},
				LengthRange: []int{2, 4096},
			},
		},
	}
	return marshalBase99Block(block)
}

func base99PairValue(pair base99Pair) int64 {
	return pair.Left + base99PairRadix*pair.Right
}

func base99PairProgram(pair base99Pair, previous int64) string {
	value := pair.Left + base99PairRadix*pair.Right
	literal := "`" + strconv.FormatInt(value, 10) + "`s"
	if value < 10 {
		literal = strconv.FormatInt(value, 10) + "s"
	}

	delta := value - previous
	operator := "+"
	if delta < 0 {
		delta = -delta
		operator = "-"
	}
	best := literal
	for digit := int64(1); digit <= 9; digit++ {
		if delta%digit != 0 {
			continue
		}
		repetitions := int(delta / digit)
		if repetitions < 1 || repetitions > 3 {
			continue
		}
		candidate := "M" + strconv.FormatInt(digit, 10) + "W" +
			strings.Repeat(operator, repetitions) + "s"
		if len(candidate) < len(best) {
			best = candidate
		}
	}
	return best
}

func base99PairTableBlock(artifact base99Artifact) ([]byte, error) {
	atoms := []string{"1Ns"}
	previous := int64(-1)
	for _, pair := range artifact.Pairs {
		atoms = append(atoms, base99PairProgram(pair, previous))
		previous = base99PairValue(pair)
	}

	content, err := base99SafeTableContent(atoms)
	if err != nil {
		return nil, err
	}
	for row := range base99TableRows {
		if row%2 == 0 {
			if row == 0 {
				content[row][0], content[row][1], content[row][2] = '>', '@', '>'
			} else {
				content[row][0], content[row][1] = '^', '>'
			}
			content[row][base99TableWidth-1] = 'v'
		} else {
			content[row][0] = '^'
			content[row][base99TableWidth-1] = '<'
			if row == base99TableRows-1 {
				content[row][1] = '<'
			} else {
				content[row][1] = 'v'
			}
		}
	}
	if !bytes.Contains(content[1], []byte(" s`7041`")) {
		return nil, fmt.Errorf("base-99 pair table lost its floor-safe 1407 literal")
	}
	content[1] = bytes.Replace(content[1], []byte(" s`7041`"), []byte("s`7041 `"), 1)

	interior := make([]string, base99TableRows)
	for row := range content {
		interior[row] = string(content[row])
	}

	expected := []int64{-1}
	for _, pair := range artifact.Pairs {
		expected = append(expected, base99PairValue(pair))
	}
	block := base75MapperDefinition{
		Name:     "history_base99_pairs",
		Size:     fmt.Sprintf("%dx%d", base99TableWidth, base99TableRows),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"pairs": {
				Type:        "output",
				Side:        "right",
				OffsetRange: []int{2, 2},
				LengthRange: []int{2, 4096},
			},
		},
		Tests: []base75BlockTest{{
			Name:     "one_dictionary_cycle",
			Expected: map[string][]int64{"pairs": expected},
		}},
	}
	return marshalBase99Block(block)
}

func base99SafeTableContent(atoms []string) ([][]byte, error) {
	var best [][]byte
	bestUnsafe := base99TableWidth + 1
	bestOdd := base99TableWidth + 1
	for first := 1; first < len(atoms)-2; first++ {
		for second := first + 1; second < len(atoms)-1; second++ {
			for third := second + 1; third < len(atoms); third++ {
				chunks := []string{
					strings.Join(atoms[:first], ""),
					strings.Join(atoms[first:second], ""),
					strings.Join(atoms[second:third], ""),
					strings.Join(atoms[third:], ""),
				}
				minimum := []int{3, 2, 2, 2}
				maximum := make([]int, base99TableRows)
				fits := true
				for row := range base99TableRows {
					maximum[row] = base99TableWidth - 1 - len(chunks[row])
					if maximum[row] < minimum[row] {
						fits = false
					}
				}
				if !fits {
					continue
				}
				for start0 := minimum[0]; start0 <= maximum[0]; start0++ {
					for start1 := minimum[1]; start1 <= maximum[1]; start1++ {
						for start2 := minimum[2]; start2 <= maximum[2]; start2++ {
							for start3 := minimum[3]; start3 <= maximum[3]; start3++ {
								starts := []int{start0, start1, start2, start3}
								rows := make([][]byte, base99TableRows)
								for row := range base99TableRows {
									rows[row] = []byte(strings.Repeat(" ", base99TableWidth))
									chunk := chunks[row]
									if row%2 == 1 {
										chunk = reverse(chunk)
									}
									copy(rows[row][starts[row]:], chunk)
								}
								if base99VerticalLiteralsSafe(rows) {
									unsafe := base99UnsafeDelimiterCount(rows)
									odd := base99OddDelimiterCount(rows)
									if unsafe < bestUnsafe ||
										(unsafe == bestUnsafe && odd < bestOdd) {
										best = rows
										bestUnsafe = unsafe
										bestOdd = odd
									}
								}
							}
						}
					}
				}
			}
		}
	}
	if best != nil {
		return best, nil
	}
	return nil, fmt.Errorf("cannot make base-99 pair table vertically literal-safe")
}

func base99VerticalLiteralsSafe(rows [][]byte) bool {
	for column := range base99TableWidth {
		var delimiters []int
		for row := range rows {
			if rows[row][column] == '`' {
				delimiters = append(delimiters, row)
			}
		}
		for index := 0; index+1 < len(delimiters); index += 2 {
			for row := delimiters[index] + 1; row < delimiters[index+1]; row++ {
				value := rows[row][column]
				if value != ' ' && (value < '0' || value > '9') {
					return false
				}
			}
		}
	}
	return true
}

func base99UnsafeDelimiterCount(rows [][]byte) int {
	// An odd number in a lowerLiteral column would pair with the first
	// delimiter in the ASCII mapper below this room.
	lowerLiteral := make(map[int]bool)
	for _, mapperColumn := range []int{
		1, 2, 4, 5, 6, 12, 15, 18, 21, 23, 25, 26, 27, 30, 31, 33, 34, 37,
	} {
		globalColumn := base99ASCIIFloorX + 1 + mapperColumn
		localColumn := globalColumn - (base99TableFloorX + 1)
		if localColumn >= 0 && localColumn < base99TableWidth {
			lowerLiteral[localColumn] = true
		}
	}
	unsafe := 0
	for column := range base99TableWidth {
		count := 0
		for row := range rows {
			if rows[row][column] == '`' {
				count++
			}
		}
		if lowerLiteral[column] && count%2 != 0 {
			unsafe++
		}
	}
	return unsafe
}

func base99OddDelimiterCount(rows [][]byte) int {
	odd := 0
	for column := range base99TableWidth {
		count := 0
		for row := range rows {
			if rows[row][column] == '`' {
				count++
			}
		}
		if count%2 != 0 {
			odd++
		}
	}
	return odd
}

func base99UnpackerBlock() ([]byte, error) {
	const width, height = 21, 3
	var variableWord, place int64 = 0, 1
	variableCodes := []int64{1, 0, 2, 3, 4, 5, 6, 7, 1}
	for _, code := range variableCodes {
		variableWord += code * place
		place *= base99Radix
	}
	block := base75MapperDefinition{
		Name: "base99_unpacker",
		Size: fmt.Sprintf("%dx%d", width, height),
		Interior: []string{
			">@r    >M `99`W/WsWXv",
			"       ^           <v",
			"^                   <",
		},
		Ports: map[string]huffmanROMPort{
			"rom": {
				Type:        "input",
				Side:        "left",
				OffsetRange: []int{1, 1},
				LengthRange: []int{2, 4096},
			},
			"codes": {
				Type:        "output",
				Side:        "bottom",
				OffsetRange: []int{20, 20},
				LengthRange: []int{2, 4096},
			},
		},
		Tests: []base75BlockTest{
			{
				Name: "eight_codes",
				Inputs: map[string][]int64{
					"rom": {4701155549599972},
				},
				Expected: map[string][]int64{
					"codes": {1, 8, 15, 22, 29, 36, 43, 50},
				},
			},
			{
				Name: "nine_codes_with_zero",
				Inputs: map[string][]int64{
					"rom": {variableWord},
				},
				Expected: map[string][]int64{
					"codes": variableCodes,
				},
			},
		},
	}
	return marshalBase99Block(block)
}

func mirrorBase99Block(data []byte, name string) ([]byte, error) {
	var block base75MapperDefinition
	if err := json.Unmarshal(data, &block); err != nil {
		return nil, err
	}
	parts := strings.Split(block.Size, "x")
	if len(parts) != 2 {
		return nil, fmt.Errorf("invalid block size %q", block.Size)
	}
	width, err := strconv.Atoi(parts[0])
	if err != nil {
		return nil, err
	}
	height, err := strconv.Atoi(parts[1])
	if err != nil {
		return nil, err
	}
	rotated := make([]string, len(block.Interior))
	for rowIndex, original := range block.Interior {
		row := []byte(original)
		for left, right := 0, len(row)-1; left <= right; left, right = left+1, right-1 {
			leftValue, rightValue := row[left], row[right]
			switch leftValue {
			case '<':
				leftValue = '>'
			case '>':
				leftValue = '<'
			case '^':
				leftValue = 'v'
			case 'v', 'V':
				leftValue = '^'
			}
			switch rightValue {
			case '<':
				rightValue = '>'
			case '>':
				rightValue = '<'
			case '^':
				rightValue = 'v'
			case 'v', 'V':
				rightValue = '^'
			}
			row[left], row[right] = rightValue, leftValue
		}
		rotated[len(block.Interior)-1-rowIndex] = string(row)
	}
	block.Interior = rotated
	for name, port := range block.Ports {
		switch port.Side {
		case "left":
			port.Side = "right"
			port.OffsetRange = []int{
				height - 1 - port.OffsetRange[len(port.OffsetRange)-1],
				height - 1 - port.OffsetRange[0],
			}
		case "right":
			port.Side = "left"
			port.OffsetRange = []int{
				height - 1 - port.OffsetRange[len(port.OffsetRange)-1],
				height - 1 - port.OffsetRange[0],
			}
		case "top":
			port.Side = "bottom"
			port.OffsetRange = []int{
				width - 1 - port.OffsetRange[len(port.OffsetRange)-1],
				width - 1 - port.OffsetRange[0],
			}
		case "bottom":
			port.Side = "top"
			port.OffsetRange = []int{
				width - 1 - port.OffsetRange[len(port.OffsetRange)-1],
				width - 1 - port.OffsetRange[0],
			}
		}
		block.Ports[name] = port
	}
	block.Name = name
	return marshalBase99Block(block)
}

func base99DigramDecoderBlock() ([]byte, error) {
	const width, height = 31, 5
	interior := []string{
		"v       s+< >`65`Ms1s`14`s4sWsv",
		">@rM`74`W-XW^ >`74`M>rmd/WsWs v",
		"^         >b>rX     ^  <      v",
		"^           ^ <               v",
		"^                             <",
	}
	block := base75MapperDefinition{
		Name:     "base99_digram_decoder",
		Size:     fmt.Sprintf("%dx%d", width, height),
		Interior: interior,
		Ports: map[string]huffmanROMPort{
			"codes": {
				Type:        "input",
				Side:        "left",
				OffsetRange: []int{3, 3},
				LengthRange: []int{2, 4096},
			},
			"pairs": {
				Type:        "input",
				Side:        "top",
				OffsetRange: []int{17, 17},
				LengthRange: []int{2, 4096},
			},
			"literals": {
				Type:        "output",
				Side:        "right",
				OffsetRange: []int{3, 3},
				LengthRange: []int{2, 4096},
			},
		},
		Tests: []base75BlockTest{{
			Name: "literal_phrase_and_first_pair",
			Inputs: map[string][]int64{
				"codes": {1, 74, 75, 73, 0},
				"pairs": {-1, 4880},
			},
			Expected: map[string][]int64{
				"literals": {1, 65, 1, 14, 4, 65, 70, 65, 73, 0},
			},
		}},
	}
	return marshalBase99Block(block)
}

func base99ASCIIMapperBlock() ([]byte, error) {
	data, err := base75MapperBlock()
	if err != nil {
		return nil, err
	}
	var block base75MapperDefinition
	if err := json.Unmarshal(data, &block); err != nil {
		return nil, err
	}
	block.Name = "base99_ascii"
	block.Size = "43x6"
	block.Interior = block.Interior[:6]
	block.Tests[0].Inputs["codes"] = []int64{
		1, 16, 17, 18, 26, 27, 52, 53, 64, 65,
		66, 67, 68, 69, 70, 71, 72, 73, 0,
	}
	block.Tests[0].Expected["bytes"] =
		block.Tests[0].Expected["bytes"][:19]
	return marshalBase99Block(block)
}

func base99ASCIIMirrorFloorSafe(data []byte) ([]byte, error) {
	var block base75MapperDefinition
	if err := json.Unmarshal(data, &block); err != nil {
		return nil, err
	}
	const before = "`113`+s      v"
	const after = "`113 `+s     v"
	if len(block.Interior) <= 4 || strings.Count(block.Interior[4], before) != 1 {
		return nil, fmt.Errorf("base-99 ASCII mapper lost its floor-safe 113 literal")
	}
	block.Interior[4] = strings.Replace(block.Interior[4], before, after, 1)
	row0 := []byte(block.Interior[0])
	row4 := []byte(block.Interior[4])
	row5 := []byte(block.Interior[5])
	row0[19] = 'v'
	copy(row0[20:38], strings.Repeat(" ", 18))
	copy(row0[22:38], reverse("`116`sM3W----s-s"))
	row0[38] = '<'
	copy(row4[0:15], ">`85`s `83`sv  ")
	row4[38] = '^'
	row5[19] = '>'
	row5[12] = '>'
	block.Interior[0], block.Interior[4], block.Interior[5] =
		string(row0), string(row4), string(row5)
	expected := block.Tests[0].Expected["bytes"]
	expected = append(expected[:4], append([]int64{85, 83}, expected[4:]...)...)
	expected = append(expected, 116, 104, 101)
	block.Tests[0].Expected["bytes"] = expected
	return marshalBase99Block(block)
}

func equalBase99Data(artifact base99Artifact, data []byte) bool {
	decoded, err := unpackBase99(artifact)
	return err == nil && bytes.Equal(decoded, data)
}
