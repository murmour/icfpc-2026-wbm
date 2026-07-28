package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"

	lmsim "sim"
)

type stagedRound struct {
	Inputs      []int64 `json:"inputs"`
	OutputCount int     `json:"output_count"`
}

// sim_rounds follows the contest harness protocol: the next matrix becomes
// available only after every output of the preceding matrix has appeared.
func main() {
	if len(os.Args) != 4 {
		fmt.Fprintln(os.Stderr, "usage: sim_rounds PROGRAM TICK_LIMIT ROUNDS_JSON")
		os.Exit(2)
	}
	code, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	program, err := lmsim.ParseProgram(string(code))
	if err != nil {
		panic(err)
	}
	tickLimit, err := strconv.Atoi(os.Args[2])
	if err != nil {
		panic(err)
	}
	rawRounds, err := os.ReadFile(os.Args[3])
	if err != nil {
		panic(err)
	}
	var rounds []stagedRound
	if err := json.Unmarshal(rawRounds, &rounds); err != nil {
		panic(err)
	}

	program.MaxTicks = tickLimit
	targetOutputs := 0
	for roundIndex, round := range rounds {
		program.InputQueue = append(program.InputQueue, round.Inputs...)
		targetOutputs += round.OutputCount
		for !program.Halted && len(program.OutputQueue) < targetOutputs {
			program.Step()
		}
		if program.Error != nil {
			fmt.Fprintf(
				os.Stderr,
				"round %d failed at tick %d: %v\n",
				roundIndex,
				program.TickCount,
				program.Error,
			)
			os.Exit(1)
		}
		if len(program.OutputQueue) != targetOutputs {
			fmt.Fprintf(
				os.Stderr,
				"round %d halted after %d of %d cumulative outputs\n",
				roundIndex,
				len(program.OutputQueue),
				targetOutputs,
			)
			os.Exit(1)
		}
	}

	encoded, err := json.Marshal(program.OutputQueue)
	if err != nil {
		panic(err)
	}
	fmt.Printf("TICKS %d\n", program.TickCount)
	fmt.Printf("OUTPUT %s\n", encoded)
}
