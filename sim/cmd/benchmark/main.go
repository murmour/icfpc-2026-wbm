package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	lmsim "sim"
)

type benchmarkCase struct {
	Name     string
	Input    []int64
	Expected []int64
}

func readBenchmarkCases(path string) ([]benchmarkCase, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var fixture struct {
		Cases []struct {
			Name   string  `json:"name"`
			Input  []int64 `json:"input"`
			Output []int64 `json:"output"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		return nil, fmt.Errorf("parse public test JSON: %w", err)
	}
	if len(fixture.Cases) == 0 {
		return nil, fmt.Errorf("no public cases found in %s", path)
	}
	cases := make([]benchmarkCase, len(fixture.Cases))
	for index, test := range fixture.Cases {
		if test.Name == "" {
			return nil, fmt.Errorf("public case %d has no name", index+1)
		}
		cases[index] = benchmarkCase{
			Name:     test.Name,
			Input:    test.Input,
			Expected: test.Output,
		}
	}
	return cases, nil
}

func runBenchmarkCase(code string, test benchmarkCase, maxTicks int) (int, error) {
	if len(test.Expected) == 0 {
		return 0, nil
	}

	program, err := lmsim.ParseProgram(code)
	if err != nil {
		return 0, err
	}
	program.MaxTicks = maxTicks
	program.InputQueue = append(program.InputQueue, test.Input...)

	outputIndex := 0
	for {
		program.Step()
		if program.Error != nil {
			return program.TickCount, program.Error
		}

		for outputIndex < len(program.OutputQueue) {
			if outputIndex >= len(test.Expected) {
				return program.TickCount, fmt.Errorf("unexpected output %d", program.OutputQueue[outputIndex])
			}
			actual := program.OutputQueue[outputIndex]
			expected := test.Expected[outputIndex]
			if actual != expected {
				return program.TickCount, fmt.Errorf(
					"output %d: got %d, want %d",
					outputIndex,
					actual,
					expected,
				)
			}
			outputIndex++
			if outputIndex == len(test.Expected) {
				return program.TickCount, nil
			}
		}

		if program.Halted {
			return program.TickCount, fmt.Errorf(
				"halted after %d of %d expected outputs",
				outputIndex,
				len(test.Expected),
			)
		}
	}
}

func main() {
	programPath := flag.String("program", "", "Little Man program to benchmark")
	testPath := flag.String("tests", "", "public test JSON")
	maxTicks := flag.Int("max-ticks", 5_000_000, "maximum ticks per case")
	flag.Parse()

	if *programPath == "" || *testPath == "" {
		flag.Usage()
		os.Exit(2)
	}

	codeBytes, err := os.ReadFile(*programPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read program: %v\n", err)
		os.Exit(1)
	}
	cases, err := readBenchmarkCases(*testPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read cases: %v\n", err)
		os.Exit(1)
	}

	parsed, err := lmsim.ParseProgram(string(codeBytes))
	if err != nil {
		fmt.Fprintf(os.Stderr, "parse program: %v\n", err)
		os.Exit(1)
	}
	side := max(parsed.Width, parsed.Height)
	footprint := side * side

	totalTicks := 0
	for _, test := range cases {
		ticks, runErr := runBenchmarkCase(string(codeBytes), test, *maxTicks)
		if runErr != nil {
			fmt.Printf("%s: FAIL at tick %d: %v\n", test.Name, ticks, runErr)
			os.Exit(1)
		}
		totalTicks += ticks
		fmt.Printf("%s: PASS tick=%d inputs=%d outputs=%d\n",
			test.Name,
			ticks,
			len(test.Input),
			len(test.Expected),
		)
	}

	averageTicks := float64(totalTicks) / float64(len(cases))
	score := float64(footprint) * averageTicks
	fmt.Printf(
		"summary: dimensions=%dx%d side=%d footprint=%d average_ticks=%.3f score=%.0f\n",
		parsed.Width,
		parsed.Height,
		side,
		footprint,
		averageTicks,
		score,
	)
}
