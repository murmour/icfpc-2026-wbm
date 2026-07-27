package main

import (
	"bufio"
	"math/rand"
	"os"
	"reflect"
	"slices"
	"strconv"
	"strings"
	"testing"
)

func TestGradeExample(t *testing.T) {
	source, err := os.ReadFile("examples/grade.plumb")
	if err != nil {
		t.Fatal(err)
	}
	program, err := parseSource(string(source))
	if err != nil {
		t.Fatal(err)
	}
	input := []int64{
		4, 4,
		1001, 1, 2, 3, 4,
		1002, 10, 20, 30, 40,
		1003, 5, 5, 5, 5,
		1004, 7, 7, 7, 7,
		4,
		1, 1002, 4,
		3, 3,
		4, 4,
		2, 1001, 3, 99,
		2,
		4, 3,
		1, 1001, 3,
	}
	machine, err := NewMachine(program, input, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(100_000)
	if err != nil {
		t.Fatal(err)
	}
	expected := []int64{40, 11, 1002, 1001, 99}
	if !reflect.DeepEqual(result.Output, expected) {
		t.Fatalf("output = %v, want %v", result.Output, expected)
	}
}

func TestGradePublicCases(t *testing.T) {
	source, err := os.ReadFile("examples/grade.plumb")
	if err != nil {
		t.Fatal(err)
	}
	program, err := parseSource(string(source))
	if err != nil {
		t.Fatal(err)
	}
	problem, err := os.Open("../../../problems/grade.md")
	if err != nil {
		t.Fatal(err)
	}
	defer problem.Close()

	type testCase struct {
		input    []int64
		expected []int64
	}
	var cases []testCase
	var current testCase
	inPublicCases := false
	scanner := bufio.NewScanner(problem)
	scanner.Buffer(make([]byte, 64*1024), 4*1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "Public test cases") {
			inPublicCases = true
			continue
		}
		if !inPublicCases {
			continue
		}
		if line == "Round 1" && len(current.input) != 0 {
			cases = append(cases, current)
			current = testCase{}
			continue
		}
		switch {
		case strings.HasPrefix(line, "in:"):
			current.input = append(
				current.input,
				parseTestIntegers(t, strings.TrimSpace(strings.TrimPrefix(line, "in:")))...,
			)
		case strings.HasPrefix(line, "out:"):
			raw := strings.TrimSpace(strings.TrimPrefix(line, "out:"))
			if raw != "(none)" {
				current.expected = append(
					current.expected,
					parseTestIntegers(t, raw)...,
				)
			}
		}
	}
	if err := scanner.Err(); err != nil {
		t.Fatal(err)
	}
	if len(current.input) != 0 {
		cases = append(cases, current)
	}
	if len(cases) != 7 {
		t.Fatalf("parsed %d public cases, want 7", len(cases))
	}

	for index, test := range cases {
		machine, machineErr := NewMachine(program, test.input, 1)
		if machineErr != nil {
			t.Fatal(machineErr)
		}
		result, runErr := machine.Run(5_000_000)
		if runErr != nil {
			t.Fatalf("case %d: %v", index+1, runErr)
		}
		if !reflect.DeepEqual(result.Output, test.expected) {
			t.Fatalf(
				"case %d output = %v, want %v",
				index+1,
				result.Output,
				test.expected,
			)
		}
	}
}

func TestReassemblyCoreCases(t *testing.T) {
	source, err := os.ReadFile("examples/reassembly.plumb")
	if err != nil {
		t.Fatal(err)
	}
	program, err := parseSource(string(source))
	if err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name     string
		input    []int64
		expected []int64
	}{
		{
			name: "in order",
			input: []int64{
				6, 0, 100, 1, 101, 2, 102, 3, 103, 4, 104, 5, 105,
			},
			expected: []int64{100, 101, 102, 103, 104, 105},
		},
		{
			name:     "shortest",
			input:    []int64{1, 0, 42},
			expected: []int64{42},
		},
		{
			name: "maximum legal displacement",
			input: []int64{
				17,
				15, 900,
				0, 100, 1, 101, 2, 102, 3, 103, 4, 104,
				5, 105, 6, 106, 7, 107, 8, 108, 9, 109,
				10, 110, 11, 111, 12, 112, 13, 113, 14, 114,
				16, 999,
			},
			expected: []int64{
				100, 101, 102, 103, 104, 105, 106, 107, 108,
				109, 110, 111, 112, 113, 114, 900, 999,
			},
		},
		{
			name: "drain burst",
			input: []int64{
				16,
				15, 215, 14, 214, 13, 213, 12, 212,
				11, 211, 10, 210, 9, 209, 8, 208,
				7, 207, 6, 206, 5, 205, 4, 204,
				3, 203, 2, 202, 1, 201, 0, 200,
			},
			expected: []int64{
				200, 201, 202, 203, 204, 205, 206, 207,
				208, 209, 210, 211, 212, 213, 214, 215,
			},
		},
		{
			name: "loss",
			input: []int64{
				20,
				1, 301, 2, 302, 3, 303, 4, 304,
				5, 305, 6, 306, 7, 307, 8, 308,
				9, 309, 10, 310, 11, 311, 12, 312,
				13, 313, 14, 314, 15, 315, 16, 316,
			},
			expected: []int64{-1},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			machine, machineErr := NewMachine(program, test.input, 1)
			if machineErr != nil {
				t.Fatal(machineErr)
			}
			result, runErr := machine.Run(1_000_000)
			if runErr != nil {
				t.Fatal(runErr)
			}
			if !reflect.DeepEqual(result.Output, test.expected) {
				t.Fatalf("output = %v, want %v", result.Output, test.expected)
			}
		})
	}
}

func parseTestIntegers(t *testing.T, raw string) []int64 {
	t.Helper()
	fields := strings.Fields(raw)
	values := make([]int64, len(fields))
	for index, field := range fields {
		value, err := strconv.ParseInt(field, 10, 64)
		if err != nil {
			t.Fatalf("parse %q: %v", field, err)
		}
		values[index] = value
	}
	return values
}

func TestInterpreterPipelineAndBackpressure(t *testing.T) {
	program := mustParse(t, `
program doubles
block main {
  forever {
    A = recv input
    send worker
  }
}
block worker {
  forever {
    A = recv main
    B = A
    A += B
    send output
  }
}
`)

	machine, err := NewMachine(program, []int64{1, -3, 0, 42}, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(1000)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != StatusWaitingInput {
		t.Fatalf("status = %s, want %s", result.Status, StatusWaitingInput)
	}
	expected := []int64{2, -6, 0, 84}
	if !reflect.DeepEqual(result.Output, expected) {
		t.Fatalf("output = %v, want %v", result.Output, expected)
	}
}

func TestInterpreterNamedPipeFIFO(t *testing.T) {
	program := mustParse(t, `
pipe queue 3..
block main {
  forever {
    A = recv input
    send queue
    A = recv input
    send queue
    A = recv input
    send queue
    A = recv queue
    send output
    A = recv queue
    send output
    A = recv queue
    send output
  }
}
`)
	machine, err := NewMachine(program, []int64{9, -2, 7}, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(100)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(result.Output, []int64{9, -2, 7}) {
		t.Fatalf("output = %v", result.Output)
	}
}

func TestInterpreterNamedPipeBackpressure(t *testing.T) {
	program := mustParse(t, `
pipe queue 2..
block main {
  forever {
    A = 1
    send queue
    A = 3
    send queue
    A = 2
    send queue
  }
}
`)
	machine, err := NewMachine(program, nil, 99)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(100)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != StatusDeadlocked ||
		result.Actors[0].Blocked != "send queue (full)" {
		t.Fatalf("result = %#v", result)
	}
}

func TestLowerNamedPipeToRelay(t *testing.T) {
	program := mustParse(t, `
pipe queue 17..
block main {
  forever {
    A = recv input
    send queue
    A = recv queue
    send output
  }
}
`)
	lowered, edges, err := lowerNamedPipes(program)
	if err != nil {
		t.Fatal(err)
	}
	if len(lowered.Pipes) != 0 || len(lowered.Blocks) != 2 ||
		lowered.Blocks[1].Name != "__pipe_queue" {
		t.Fatalf("lowered program = %#v", lowered)
	}
	foundStorageLeg := false
	for _, edge := range edges {
		if edge.Source == "__pipe_queue" &&
			edge.Destination == "main" &&
			edge.MinSize == 17 &&
			edge.MaxSize == 1_000_000 {
			foundStorageLeg = true
		}
	}
	if !foundStorageLeg {
		t.Fatalf("edges = %#v", edges)
	}
}

func TestInterpreterNestedStructuredControl(t *testing.T) {
	program := mustParse(t, `
block main {
  forever {
    A = recv input
    repeat A {
      A = recv input
      if sign A {
        negative {
          A = -A
          send output
        }
        zero {
          A = 7
          send output
        }
        positive {
          B = A
          A += B
          send output
        }
      }
    }
  }
}
`)

	machine, err := NewMachine(program, []int64{3, -4, 0, 5}, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(1000)
	if err != nil {
		t.Fatal(err)
	}
	expected := []int64{4, 7, 10}
	if !reflect.DeepEqual(result.Output, expected) {
		t.Fatalf("output = %v, want %v", result.Output, expected)
	}
}

func TestInterpreterWhilePositive(t *testing.T) {
	program := mustParse(t, `
block main {
  forever {
    A = recv input
    while positive A {
      send output
      A = recv input
    }
  }
}
`)
	machine, err := NewMachine(program, []int64{3, 2, 1, 0, 4, 0}, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(1000)
	if err != nil {
		t.Fatal(err)
	}
	expected := []int64{3, 2, 1, 4}
	if !reflect.DeepEqual(result.Output, expected) {
		t.Fatalf("output = %v, want %v", result.Output, expected)
	}
}

func TestInterpreterReportsDeadlock(t *testing.T) {
	program := mustParse(t, `
block main {
  forever {
    A = recv worker
  }
}
block worker {
  forever {
    A = recv main
  }
}
`)
	machine, err := NewMachine(program, nil, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(100)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != StatusDeadlocked {
		t.Fatalf("status = %s, want %s", result.Status, StatusDeadlocked)
	}
}

func TestBubbleSortExample(t *testing.T) {
	program, err := parseFile("examples/bubble_sort.plumb")
	if err != nil {
		t.Fatal(err)
	}
	input := []int64{
		3, 3, 1, 2,
		1, 42,
		4, 7, 7, 7, 7,
		16, 10000, -10000, 5, 5, -5, -5, 0, 3, -3,
		10000, -10000, 1, -1, 2, -2, 0,
	}
	expected := []int64{
		1, 2, 3,
		42,
		7, 7, 7, 7,
		-10000, -10000, -5, -5, -3, -2, -1, 0,
		0, 1, 2, 3, 5, 5, 10000, 10000,
	}
	machine, err := NewMachine(program, input, 8)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(1_000_000)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != StatusWaitingInput {
		t.Fatalf("status = %s, want %s", result.Status, StatusWaitingInput)
	}
	if !reflect.DeepEqual(result.Output, expected) {
		t.Fatalf("output = %v, want %v", result.Output, expected)
	}
}

func TestBubbleSortRandomRounds(t *testing.T) {
	program, err := parseFile("examples/bubble_sort.plumb")
	if err != nil {
		t.Fatal(err)
	}

	random := rand.New(rand.NewSource(20260727))
	var input []int64
	var expected []int64
	for range 200 {
		length := 1 + random.Intn(16)
		values := make([]int64, length)
		input = append(input, int64(length))
		for index := range values {
			values[index] = int64(random.Intn(20001) - 10000)
			input = append(input, values[index])
		}
		slices.Sort(values)
		expected = append(expected, values...)
	}

	machine, err := NewMachine(program, input, 8)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(5_000_000)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != StatusWaitingInput {
		t.Fatalf("status = %s, want %s", result.Status, StatusWaitingInput)
	}
	if !reflect.DeepEqual(result.Output, expected) {
		t.Fatalf("output = %v, want %v", result.Output, expected)
	}
}

func TestThreeCellSortExample(t *testing.T) {
	program, err := parseFile("examples/sort_chain3.plumb")
	if err != nil {
		t.Fatal(err)
	}
	input := []int64{
		3, 3, 1, 2,
		1, 42,
		3, 10000, -10000, 0,
	}
	machine, err := NewMachine(program, input, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(100000)
	if err != nil {
		t.Fatal(err)
	}
	expected := []int64{1, 2, 3, 42, -10000, 0, 10000}
	if !reflect.DeepEqual(result.Output, expected) {
		t.Fatalf("output = %v, want %v", result.Output, expected)
	}
}

func TestThreeCellSortRandomRounds(t *testing.T) {
	program, err := parseFile("examples/sort_chain3.plumb")
	if err != nil {
		t.Fatal(err)
	}

	random := rand.New(rand.NewSource(20260726))
	var input []int64
	var expected []int64
	for range 200 {
		length := 1 + random.Intn(3)
		values := make([]int64, length)
		input = append(input, int64(length))
		for index := range values {
			values[index] = int64(random.Intn(20001) - 10000)
			input = append(input, values[index])
		}
		slices.Sort(values)
		expected = append(expected, values...)
	}

	machine, err := NewMachine(program, input, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := machine.Run(1_000_000)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != StatusWaitingInput {
		t.Fatalf("status = %s, want %s", result.Status, StatusWaitingInput)
	}
	if !reflect.DeepEqual(result.Output, expected) {
		t.Fatalf("output = %v, want %v", result.Output, expected)
	}
}

func mustParse(t *testing.T, source string) *Program {
	t.Helper()
	program, err := parseSource(source)
	if err != nil {
		t.Fatalf("parseSource returned an error: %v", err)
	}
	return program
}
