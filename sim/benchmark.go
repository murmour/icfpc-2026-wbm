package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type benchmarkCase struct {
	Input    []int64
	Expected []int64
}

func parseIntList(raw string) ([]int64, error) {
	if strings.TrimSpace(raw) == "(none)" {
		return []int64{}, nil
	}
	fields := strings.Fields(raw)
	values := make([]int64, 0, len(fields))
	for _, field := range fields {
		value, err := strconv.ParseInt(field, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("parse integer %q: %w", field, err)
		}
		values = append(values, value)
	}
	return values, nil
}

func readBenchmarkCases(path string) ([]benchmarkCase, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var cases []benchmarkCase
	var pendingInput []int64
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), 4*1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		switch {
		case strings.HasPrefix(line, "in:"):
			if pendingInput != nil {
				return nil, fmt.Errorf("input without matching output")
			}
			pendingInput, err = parseIntList(strings.TrimSpace(strings.TrimPrefix(line, "in:")))
			if err != nil {
				return nil, err
			}
		case strings.HasPrefix(line, "out:") && pendingInput != nil:
			expected, parseErr := parseIntList(strings.TrimSpace(strings.TrimPrefix(line, "out:")))
			if parseErr != nil {
				return nil, parseErr
			}
			cases = append(cases, benchmarkCase{Input: pendingInput, Expected: expected})
			pendingInput = nil
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	if pendingInput != nil {
		return nil, fmt.Errorf("input without matching output")
	}
	if len(cases) == 0 {
		return nil, fmt.Errorf("no public cases found in %s", path)
	}
	return cases, nil
}

func runBenchmarkCase(code string, test benchmarkCase, maxTicks int) (int, error) {
	if len(test.Expected) == 0 {
		return 0, nil
	}

	program, err := ParseProgram(code)
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
	problemPath := flag.String("problem", "", "problem Markdown containing public in:/out: cases")
	maxTicks := flag.Int("max-ticks", 5_000_000, "maximum ticks per case")
	flag.Parse()

	if *programPath == "" || *problemPath == "" {
		flag.Usage()
		os.Exit(2)
	}

	codeBytes, err := os.ReadFile(*programPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read program: %v\n", err)
		os.Exit(1)
	}
	cases, err := readBenchmarkCases(*problemPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read cases: %v\n", err)
		os.Exit(1)
	}

	parsed, err := ParseProgram(string(codeBytes))
	if err != nil {
		fmt.Fprintf(os.Stderr, "parse program: %v\n", err)
		os.Exit(1)
	}
	side := max(parsed.Width, parsed.Height)
	footprint := side * side

	totalTicks := 0
	for index, test := range cases {
		ticks, runErr := runBenchmarkCase(string(codeBytes), test, *maxTicks)
		if runErr != nil {
			fmt.Printf("case %d: FAIL at tick %d: %v\n", index+1, ticks, runErr)
			os.Exit(1)
		}
		totalTicks += ticks
		fmt.Printf("case %d: PASS tick=%d inputs=%d outputs=%d\n",
			index+1,
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
