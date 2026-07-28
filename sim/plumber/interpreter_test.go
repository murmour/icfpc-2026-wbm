package main

import (
	"encoding/json"
	"math/rand"
	"os"
	"reflect"
	"slices"
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
	data, err := os.ReadFile("../../public_tests/grade.json")
	if err != nil {
		t.Fatal(err)
	}

	type testCase struct {
		Name   string  `json:"name"`
		Input  []int64 `json:"input"`
		Output []int64 `json:"output"`
	}
	var fixture struct {
		Cases []testCase `json:"cases"`
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Cases) != 7 {
		t.Fatalf("loaded %d public cases, want 7", len(fixture.Cases))
	}

	for _, test := range fixture.Cases {
		t.Run(test.Name, func(t *testing.T) {
			machine, machineErr := NewMachine(program, test.Input, 1)
			if machineErr != nil {
				t.Fatal(machineErr)
			}
			result, runErr := machine.Run(5_000_000)
			if runErr != nil {
				t.Fatal(runErr)
			}
			if !reflect.DeepEqual(result.Output, test.Output) {
				t.Fatalf("output = %v, want %v", result.Output, test.Output)
			}
		})
	}
}

func TestReassemblyPublicCases(t *testing.T) {
	source, err := os.ReadFile("examples/reassembly.plumb")
	if err != nil {
		t.Fatal(err)
	}
	program, err := parseSource(string(source))
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile("../../public_tests/reassembly.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []struct {
			Name   string  `json:"name"`
			Input  []int64 `json:"input"`
			Output []int64 `json:"output"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}

	for _, test := range fixture.Cases {
		t.Run(test.Name, func(t *testing.T) {
			machine, machineErr := NewMachine(program, test.Input, 1)
			if machineErr != nil {
				t.Fatal(machineErr)
			}
			result, runErr := machine.Run(1_000_000)
			if runErr != nil {
				t.Fatal(runErr)
			}
			if !reflect.DeepEqual(result.Output, test.Output) {
				t.Fatalf("output = %v, want %v", result.Output, test.Output)
			}
		})
	}
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
