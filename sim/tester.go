package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
)

type PortDef struct {
	Type        string `json:"type"` // "input" or "output"
	Side        string `json:"side"` // "top", "bottom", "left", "right"
	OffsetRange []int  `json:"offset_range"`
	LengthRange []int  `json:"length_range"`
}

type TestInstance struct {
	Name      string             `json:"name"`
	Inputs    map[string][]int64 `json:"inputs"`
	Expected  map[string][]int64 `json:"expected"`
	Loopbacks map[string]string  `json:"loopbacks"`
}

type BlockDef struct {
	Name     string             `json:"name"`
	Size     string             `json:"size"`
	Interior []string           `json:"interior"`
	Ports    map[string]PortDef `json:"ports"`
	Tests    []TestInstance     `json:"tests"`
}

func buildGrid(w, h int) [][]byte {
	grid := make([][]byte, h)
	for i := range grid {
		grid[i] = make([]byte, w)
		for j := range grid[i] {
			grid[i][j] = ' '
		}
	}
	return grid
}

func drawRoom(grid [][]byte, x, y, w, h int, interior []string) {
	for i := 0; i < w; i++ {
		grid[y][x+i] = '-'
		grid[y+h-1][x+i] = '-'
	}
	for i := 0; i < h; i++ {
		grid[y+i][x] = '|'
		grid[y+i][x+w-1] = '|'
	}
	grid[y][x] = '+'
	grid[y][x+w-1] = '+'
	grid[y+h-1][x] = '+'
	grid[y+h-1][x+w-1] = '+'

	for i, row := range interior {
		for j := 0; j < len(row); j++ {
			grid[y+1+i][x+1+j] = row[j]
		}
	}
}

func gridToStr(grid [][]byte) string {
	var out []string
	for _, row := range grid {
		out = append(out, string(row))
	}
	return strings.Join(out, "\n")
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run tester.go <file.block>")
		os.Exit(1)
	}

	blockFile := os.Args[1]
	b, err := os.ReadFile(blockFile)
	if err != nil {
		fmt.Printf("Error reading block file: %v\n", err)
		os.Exit(1)
	}

	var def BlockDef
	if err := json.Unmarshal(b, &def); err != nil {
		fmt.Printf("Error parsing JSON: %v\n", err)
		os.Exit(1)
	}

	parts := strings.Split(def.Size, "x")
	w, _ := strconv.Atoi(parts[0])
	h, _ := strconv.Atoi(parts[1])
	allSuccess := true

	for i, row := range def.Interior {
		if len(row) < w {
			def.Interior[i] = row + strings.Repeat(" ", w-len(row))
		}
	}

	for testIdx, testDef := range def.Tests {
		if only := os.Getenv("BLOCK_TEST_ONLY"); only != "" &&
			only != strconv.Itoa(testIdx+1) {
			continue
		}
		fmt.Printf("Running Test %d: %s\n", testIdx+1, testDef.Name)

		portsPerSide := make(map[string]int)
		maxPortsOnSide := 0
		for _, port := range def.Ports {
			side := port.Side
			if side == "any" {
				side = "bottom"
			}
			portsPerSide[side]++
			if portsPerSide[side] > maxPortsOnSide {
				maxPortsOnSide = portsPerSide[side]
			}
		}
		margin := 20 + maxPortsOnSide*5
		grid := buildGrid(w+2*margin+20, h+2*margin+20)
		bx, by := margin, margin
		drawRoom(grid, bx, by, w+2, h+2, def.Interior)

		// Fake room with a man in an infinite loop to satisfy parser
		drawRoom(grid, 5, 5, 5, 5, []string{
			"@v ",
			" >v",
			" ^<",
		})

		portRooms := make(map[string]Point)
		sidePortIdx := make(map[string]int)

		type namedPort struct {
			name string
			port PortDef
		}
		orderedPorts := make([]namedPort, 0, len(def.Ports))
		for name, port := range def.Ports {
			if port.Side == "any" {
				port.Side = "bottom"
			}
			orderedPorts = append(orderedPorts, namedPort{name: name, port: port})
		}
		sort.Slice(orderedPorts, func(i, j int) bool {
			left, right := orderedPorts[i], orderedPorts[j]
			if left.port.Side != right.port.Side {
				return left.port.Side < right.port.Side
			}
			if left.port.OffsetRange[0] != right.port.OffsetRange[0] {
				return left.port.OffsetRange[0] < right.port.OffsetRange[0]
			}
			return left.name < right.name
		})

		for _, named := range orderedPorts {
			name, port := named.name, named.port
			offset := port.OffsetRange[0]
			stagger := sidePortIdx[port.Side] * 5
			sidePortIdx[port.Side]++

			rx, ry := 0, 0
			px, py := 0, 0

			if port.Side == "bottom" {
				rx = bx + 1 + offset
				ry = by + h + 5 + stagger
				px = bx + 1 + offset
				py = by + h + 2
				end_py := ry - 2
				for y := py; y <= end_py; y++ {
					if port.Type == "input" {
						grid[y][px] = '^'
					} else {
						grid[y][px] = 'v'
					}
				}
			} else if port.Side == "top" {
				rx = bx + 1 + offset
				ry = by - 5 - stagger
				px = bx + 1 + offset
				py = by - 1
				end_py := ry + 1
				for y := py; y >= end_py; y-- {
					if port.Type == "input" {
						grid[y][px] = 'v'
					} else {
						grid[y][px] = '^'
					}
				}
			} else if port.Side == "left" {
				rx = bx - 5 - stagger
				ry = by + 1 + offset
				px = bx - 1
				end_px := rx + 1
				py = by + 1 + offset
				for x := px; x >= end_px; x-- {
					if port.Type == "input" {
						grid[py][x] = '>'
					} else {
						grid[py][x] = '<'
					}
				}
			} else if port.Side == "right" {
				rx = bx + w + 5 + stagger
				ry = by + 1 + offset
				px = bx + w + 2
				end_px := rx - 2
				py = by + 1 + offset
				for x := px; x <= end_px; x++ {
					if port.Type == "input" {
						grid[py][x] = '<'
					} else {
						grid[py][x] = '>'
					}
				}
			}

			// Draw dummy 2x2 room
			grid[ry-1][rx-1] = '+'
			grid[ry-1][rx] = '+'
			grid[ry][rx-1] = '+'
			grid[ry][rx] = '+'

			portRooms[name] = Point{X: rx - 1, Y: ry - 1}
		}

		progStr := gridToStr(grid)

		prog, err := ParseProgram(progStr)
		if err != nil {
			fmt.Printf("Parse error in test %d: %v\n", testIdx+1, err)
			allSuccess = false
			continue
		}

		inPipes := make(map[string]*Pipe)
		outPipes := make(map[string]*Pipe)

		for name, pt := range portRooms {
			var dummy *Room
			for _, r := range prog.Rooms {
				if r.MinX == pt.X && r.MinY == pt.Y {
					dummy = r
					break
				}
			}
			if dummy == nil {
				fmt.Printf("Could not find dummy room for port %s\n", name)
				allSuccess = false
				continue
			}

			if def.Ports[name].Type == "input" {
				for _, p := range prog.Pipes {
					if p.SourceRoom == dummy {
						inPipes[name] = p
						break
					}
				}
			} else {
				for _, p := range prog.Pipes {
					if p.DestRoom == dummy {
						outPipes[name] = p
						break
					}
				}
			}
		}

		fmt.Printf("Found %d input pipes and %d output pipes\n", len(inPipes), len(outPipes))

		prog.MaxTicks = 500000

		inQueues := make(map[string][]int64)
		for name, vals := range testDef.Inputs {
			inQueues[name] = append([]int64(nil), vals...)
		}

		actualOut := make(map[string][]int64)
		actualOutTicks := make(map[string][]int)

		for !prog.Halted && prog.Error == nil {
			for name, p := range inPipes {
				if len(inQueues[name]) > 0 {
					if p.Values[0] == nil {
						val := inQueues[name][0]
						p.Values[0] = &val
						inQueues[name] = inQueues[name][1:]
					}
				}
			}

			prog.Step()

			for name, p := range outPipes {
				lastIdx := len(p.Path) - 1
				if p.Values[lastIdx] != nil {
					value := *p.Values[lastIdx]
					actualOut[name] = append(actualOut[name], value)
					actualOutTicks[name] = append(actualOutTicks[name], prog.TickCount)
					if inputName, ok := testDef.Loopbacks[name]; ok {
						inQueues[inputName] = append(inQueues[inputName], value)
					}
					prog.SetPipeVal(p.Path[lastIdx], nil)
				}
			}

			allExpectedMet := true
			for name, exp := range testDef.Expected {
				if len(actualOut[name]) < len(exp) {
					allExpectedMet = false
				}
			}
			if allExpectedMet {
				break
			}
		}

		success := prog.Error == nil
		if prog.Error != nil {
			fmt.Printf("  FAIL: simulator error at tick %d: %v\n", prog.TickCount, prog.Error)
		}
		for name, exp := range testDef.Expected {
			actual := actualOut[name]
			fmt.Printf(
				"Port %s outputted %d values at ticks %v: %v\n",
				name,
				len(actual),
				actualOutTicks[name],
				actual,
			)
			if len(actual) != len(exp) {
				fmt.Printf("  FAIL: Expected exactly %d values, got %d\n", len(exp), len(actual))
				success = false
				continue
			}
			for i, v := range exp {
				if actual[i] != v {
					fmt.Printf("  FAIL at index %d: Expected %d, got %d\n", i, v, actual[i])
					success = false
					break
				}
			}
		}

		if success {
			fmt.Printf("TEST %d PASSED!\n", testIdx+1)
		} else {
			fmt.Printf("TEST %d FAILED.\n", testIdx+1)
			allSuccess = false
		}
	}
	if !allSuccess {
		os.Exit(1)
	}
}
