package main

import (
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
)

func main() {
	programPath := flag.String("program", "", "Plumber source file")
	manPath := flag.String("man", "", "Compile to this .man file instead of interpreting")
	floorplanMode := flag.String(
		"floorplan-mode",
		"shelf",
		"Floorplanning mode for -man: shelf or anneal",
	)
	inputText := flag.String("input", "", "Space-separated external input values")
	channelCapacity := flag.Int("channel-capacity", 1, "Capacity of each directed channel")
	maxSteps := flag.Int64("max-steps", 1_000_000, "Maximum executed instructions")
	showActors := flag.Bool("actors", false, "Print final actor registers and blocked states")
	flag.Parse()

	if *programPath == "" {
		flag.Usage()
		os.Exit(2)
	}
	program, err := parseFile(*programPath)
	if err != nil {
		fatal(err)
	}
	if *manPath != "" {
		if err := compileMan(program, *manPath, *floorplanMode); err != nil {
			fatal(err)
		}
		fmt.Printf("Wrote %s\n", *manPath)
		return
	}

	input, err := parseInput(*inputText)
	if err != nil {
		fatal(err)
	}
	machine, err := NewMachine(program, input, *channelCapacity)
	if err != nil {
		fatal(err)
	}
	result, err := machine.Run(*maxSteps)
	if err != nil {
		fatal(err)
	}

	fmt.Printf("Program: %s\n", program.Name)
	fmt.Printf("Status: %s\n", result.Status)
	fmt.Printf("Steps: %d\n", result.Steps)
	fmt.Printf("Output: %v\n", result.Output)
	if blocked := formatBlocked(result.Actors); blocked != "" {
		fmt.Printf("Blocked: %s\n", blocked)
	}
	if *showActors {
		for _, current := range result.Actors {
			fmt.Printf(
				"Actor %s: A=%d B=%d halted=%t blocked=%q\n",
				current.Name,
				current.A,
				current.B,
				current.Halted,
				current.Blocked,
			)
		}
	}
}

func parseInput(raw string) ([]int64, error) {
	var result []int64
	for _, field := range strings.Fields(raw) {
		value, err := strconv.ParseInt(field, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid input value %q: %w", field, err)
		}
		result = append(result, value)
	}
	return result, nil
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "plumber:", err)
	os.Exit(1)
}
