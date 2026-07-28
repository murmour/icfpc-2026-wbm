package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"

	lmsim "sim"
)

type Probe struct {
	Edge   string `json:"edge"`
	X      int    `json:"x"`
	Y      int    `json:"y"`
	DX     int    `json:"dx"`
	DY     int    `json:"dy"`
	NextX  int    `json:"next_x"`
	NextY  int    `json:"next_y"`
	NextDX int    `json:"next_dx"`
	NextDY int    `json:"next_dy"`
}

type Snapshot struct {
	ID     int
	X, Y   int
	DX, DY int
}

type ProfileResult struct {
	Ticks   int            `json:"ticks"`
	Outputs int            `json:"outputs"`
	Counts  map[string]int `json:"counts"`
}

func matchesProbe(man Snapshot, probe Probe) bool {
	return man.X == probe.X &&
		man.Y == probe.Y &&
		man.DX == probe.DX &&
		man.DY == probe.DY
}

func matchesDestination(man *lmsim.LittleMan, probe Probe) bool {
	return man.X == probe.NextX &&
		man.Y == probe.NextY &&
		man.DX == probe.NextDX &&
		man.DY == probe.NextDY
}

func main() {
	if len(os.Args) < 5 {
		fmt.Fprintln(
			os.Stderr,
			"usage: profile_edges PROGRAM PROBES_JSON OUTPUT_COUNT "+
				"TICK_LIMIT [INPUT...]",
		)
		os.Exit(2)
	}
	code, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	probeCode, err := os.ReadFile(os.Args[2])
	if err != nil {
		panic(err)
	}
	var probes []Probe
	if err := json.Unmarshal(probeCode, &probes); err != nil {
		panic(err)
	}
	outputCount, err := strconv.Atoi(os.Args[3])
	if err != nil {
		panic(err)
	}
	tickLimit, err := strconv.Atoi(os.Args[4])
	if err != nil {
		panic(err)
	}
	program, err := lmsim.ParseProgram(string(code))
	if err != nil {
		panic(err)
	}
	program.MaxTicks = tickLimit
	for _, raw := range os.Args[5:] {
		value, parseErr := strconv.ParseInt(raw, 10, 64)
		if parseErr != nil {
			panic(parseErr)
		}
		program.InputQueue = append(program.InputQueue, value)
	}

	bySource := make(map[Snapshot][]Probe)
	counts := make(map[string]int)
	for _, probe := range probes {
		key := Snapshot{
			X: probe.X, Y: probe.Y,
			DX: probe.DX, DY: probe.DY,
		}
		bySource[key] = append(bySource[key], probe)
		counts[probe.Edge] = 0
	}

	for !program.Halted &&
		program.Error == nil &&
		(outputCount < 0 || len(program.OutputQueue) < outputCount) {
		before := make(map[int]Snapshot)
		candidates := make(map[int][]Probe)
		for _, man := range program.Men {
			if man.Halted {
				continue
			}
			snapshot := Snapshot{
				ID: man.ID,
				X:  man.X, Y: man.Y,
				DX: man.DX, DY: man.DY,
			}
			before[man.ID] = snapshot
			key := snapshot
			key.ID = 0
			if matched := bySource[key]; len(matched) != 0 {
				candidates[man.ID] = matched
			}
		}

		program.Step()
		after := make(map[int]*lmsim.LittleMan)
		var born []*lmsim.LittleMan
		for _, man := range program.Men {
			after[man.ID] = man
			if man.BornTick == program.TickCount {
				born = append(born, man)
			}
		}
		for manID, matched := range candidates {
			for _, probe := range matched {
				if man := after[manID]; man != nil &&
					matchesDestination(man, probe) {
					counts[probe.Edge]++
					continue
				}
				// Y replaces the original ID by two newly born men.  Matching
				// their first cells counts each spawned edge exactly once.
				for _, man := range born {
					if matchesDestination(man, probe) {
						counts[probe.Edge]++
						break
					}
				}
			}
		}
	}
	if program.Error != nil {
		fmt.Fprintf(
			os.Stderr,
			"simulation failed at tick %d: %v\n",
			program.TickCount,
			program.Error,
		)
		os.Exit(1)
	}
	if outputCount >= 0 && len(program.OutputQueue) < outputCount {
		fmt.Fprintf(
			os.Stderr,
			"simulation stopped at tick %d with %d/%d outputs\n",
			program.TickCount,
			len(program.OutputQueue),
			outputCount,
		)
		os.Exit(1)
	}
	result := ProfileResult{
		Ticks:   program.TickCount,
		Outputs: len(program.OutputQueue),
		Counts:  counts,
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(result); err != nil {
		panic(err)
	}
}
