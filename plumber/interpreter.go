package main

import (
	"fmt"
	"math"
	"strings"
)

type Status string

const (
	StatusHalted       Status = "halted"
	StatusWaitingInput Status = "waiting-input"
	StatusDeadlocked   Status = "deadlocked"
	StatusStepLimit    Status = "step-limit"
)

type RunResult struct {
	Status Status
	Steps  int64
	Output []int64
	Actors []ActorState
}

type ActorState struct {
	Name    string
	A       int64
	B       int64
	Halted  bool
	Blocked string
}

type channelKey struct {
	source      string
	destination string
}

type executionFrame struct {
	body      []Stmt
	index     int
	remaining int64
	forever   bool
	whilePos  bool
}

type actor struct {
	name    string
	a       int64
	b       int64
	halted  bool
	blocked string
	frames  []executionFrame
}

type Machine struct {
	actors          []*actor
	channels        map[channelKey][]int64
	channelCapacity int
	pipes           map[string][]int64
	pipeCapacities  map[string]int
	input           []int64
	inputIndex      int
	output          []int64
	steps           int64
}

func NewMachine(program *Program, input []int64, channelCapacity int) (*Machine, error) {
	if channelCapacity < 1 {
		return nil, fmt.Errorf("channel capacity must be at least 1")
	}
	if err := validateProgram(program); err != nil {
		return nil, err
	}

	machine := &Machine{
		channels:        make(map[channelKey][]int64),
		channelCapacity: channelCapacity,
		pipes:           make(map[string][]int64),
		pipeCapacities:  make(map[string]int),
		input:           append([]int64(nil), input...),
	}
	for _, pipe := range program.Pipes {
		machine.pipes[pipe.Name] = nil
		machine.pipeCapacities[pipe.Name] = pipe.MinSize
	}

	ordered := make([]*Block, 0, len(program.Blocks))
	for _, block := range program.Blocks {
		if block.Name == "main" {
			ordered = append(ordered, block)
			break
		}
	}
	for _, block := range program.Blocks {
		if block.Name != "main" {
			ordered = append(ordered, block)
		}
	}
	for _, block := range ordered {
		machine.actors = append(machine.actors, &actor{
			name: block.Name,
			frames: []executionFrame{{
				body:    block.Body,
				forever: true,
			}},
		})
	}
	return machine, nil
}

func (machine *Machine) Run(maxSteps int64) (RunResult, error) {
	if maxSteps < 1 {
		return RunResult{}, fmt.Errorf("max steps must be at least 1")
	}

	for machine.steps < maxSteps {
		progressed := false
		live := false
		for _, current := range machine.actors {
			if current.halted {
				continue
			}
			live = true
			didProgress, err := machine.stepActor(current)
			if err != nil {
				return machine.result(StatusDeadlocked), err
			}
			progressed = progressed || didProgress
			if machine.steps >= maxSteps {
				break
			}
		}

		if !live {
			return machine.result(StatusHalted), nil
		}
		if !progressed {
			status := StatusDeadlocked
			if machine.channelsEmpty() {
				for _, current := range machine.actors {
					if current.blocked == "recv input" {
						status = StatusWaitingInput
						break
					}
				}
			}
			return machine.result(status), nil
		}
	}
	return machine.result(StatusStepLimit), nil
}

func (machine *Machine) stepActor(current *actor) (bool, error) {
	current.blocked = ""
	for controlSteps := 0; controlSteps < 10000; controlSteps++ {
		if len(current.frames) == 0 {
			current.halted = true
			return true, nil
		}

		frame := &current.frames[len(current.frames)-1]
		if frame.index >= len(frame.body) {
			switch {
			case frame.forever:
				if len(frame.body) == 0 {
					return false, fmt.Errorf("block %s has an empty forever loop", current.name)
				}
				frame.index = 0
			case frame.whilePos && current.a > 0:
				frame.index = 0
			case frame.remaining > 1:
				frame.remaining--
				frame.index = 0
			default:
				current.frames = current.frames[:len(current.frames)-1]
			}
			continue
		}

		statement := frame.body[frame.index]
		switch value := statement.(type) {
		case Instruction:
			progressed, err := machine.executeInstruction(current, value)
			if err != nil || !progressed {
				return progressed, err
			}
			frame.index++
			machine.steps++
			return true, nil
		case Repeat:
			frame.index++
			if current.a > 0 && len(value.Body) > 0 {
				current.frames = append(current.frames, executionFrame{
					body:      value.Body,
					remaining: current.a,
				})
			}
		case WhilePositive:
			frame.index++
			if current.a > 0 {
				current.frames = append(current.frames, executionFrame{
					body:     value.Body,
					whilePos: true,
				})
			}
		case SignBranch:
			frame.index++
			body := value.Zero
			if current.a < 0 {
				body = value.Negative
			} else if current.a > 0 {
				body = value.Positive
			}
			if len(body) > 0 {
				current.frames = append(current.frames, executionFrame{
					body:      body,
					remaining: 1,
				})
			}
		default:
			return false, fmt.Errorf("block %s has unsupported statement %T", current.name, statement)
		}
	}
	return false, fmt.Errorf("block %s exceeded the control-flow transition limit", current.name)
}

func (machine *Machine) executeInstruction(
	current *actor,
	instruction Instruction,
) (bool, error) {
	switch instruction.Kind {
	case InstructionLoad:
		current.a = instruction.Value
	case InstructionCopy:
		current.b = current.a
	case InstructionSwap:
		current.a, current.b = current.b, current.a
	case InstructionAdd:
		current.a += current.b
	case InstructionSubtract:
		current.a -= current.b
	case InstructionMultiply:
		current.a *= current.b
	case InstructionModulo:
		if current.b == 0 {
			current.a = 0
		} else {
			current.a %= current.b
			if (current.a < 0 && current.b > 0) ||
				(current.a > 0 && current.b < 0) {
				current.a += current.b
			}
		}
	case InstructionDivide:
		divide(current)
	case InstructionNegate:
		current.a = -current.a
	case InstructionAnd:
		current.a &= current.b
	case InstructionOr:
		current.a |= current.b
	case InstructionXor:
		current.a ^= current.b
	case InstructionShiftLeft:
		if current.b < 0 || current.b > 63 {
			current.a = 0
		} else {
			current.a <<= current.b
		}
	case InstructionShiftRight:
		switch {
		case current.b < 0:
			current.a = 0
		case current.b > 63 && current.a < 0:
			current.a = -1
		case current.b > 63:
			current.a = 0
		default:
			current.a >>= current.b
		}
	case InstructionReceive:
		value, ok := machine.receive(current.name, instruction.Peer)
		if !ok {
			current.blocked = "recv " + instruction.Peer
			return false, nil
		}
		current.a = value
	case InstructionSend:
		if !machine.send(current.name, instruction.Peer, current.a) {
			current.blocked = "send " + instruction.Peer + " (full)"
			return false, nil
		}
	case InstructionHalt:
		current.halted = true
	case InstructionNop:
	default:
		return false, fmt.Errorf(
			"line %d: unsupported instruction %q",
			instruction.Line,
			instruction.Kind,
		)
	}
	return true, nil
}

func divide(current *actor) {
	if current.b == 0 {
		current.a = 0
		return
	}
	if current.a == math.MinInt64 && current.b == -1 {
		current.a = math.MinInt64
		current.b = 0
		return
	}

	quotient := current.a / current.b
	remainder := current.a % current.b
	if (current.a < 0) != (current.b < 0) && remainder != 0 {
		quotient--
		remainder += current.b
	}
	current.a = quotient
	current.b = remainder
}

func (machine *Machine) receive(destination, source string) (int64, bool) {
	if source == "input" {
		if machine.inputIndex >= len(machine.input) {
			return 0, false
		}
		value := machine.input[machine.inputIndex]
		machine.inputIndex++
		return value, true
	}
	if queue, exists := machine.pipes[source]; exists {
		if len(queue) == 0 {
			return 0, false
		}
		value := queue[0]
		machine.pipes[source] = queue[1:]
		return value, true
	}

	key := channelKey{source: source, destination: destination}
	queue := machine.channels[key]
	if len(queue) == 0 {
		return 0, false
	}
	value := queue[0]
	machine.channels[key] = queue[1:]
	return value, true
}

func (machine *Machine) send(source, destination string, value int64) bool {
	if destination == "output" {
		machine.output = append(machine.output, value)
		return true
	}
	if queue, exists := machine.pipes[destination]; exists {
		if len(queue) >= machine.pipeCapacities[destination] {
			return false
		}
		machine.pipes[destination] = append(queue, value)
		return true
	}

	key := channelKey{source: source, destination: destination}
	queue := machine.channels[key]
	if len(queue) >= machine.channelCapacity {
		return false
	}
	machine.channels[key] = append(queue, value)
	return true
}

func (machine *Machine) channelsEmpty() bool {
	for _, queue := range machine.channels {
		if len(queue) != 0 {
			return false
		}
	}
	for _, queue := range machine.pipes {
		if len(queue) != 0 {
			return false
		}
	}
	return true
}

func (machine *Machine) result(status Status) RunResult {
	result := RunResult{
		Status: status,
		Steps:  machine.steps,
		Output: append([]int64(nil), machine.output...),
		Actors: make([]ActorState, 0, len(machine.actors)),
	}
	for _, current := range machine.actors {
		result.Actors = append(result.Actors, ActorState{
			Name:    current.name,
			A:       current.a,
			B:       current.b,
			Halted:  current.halted,
			Blocked: current.blocked,
		})
	}
	return result
}

func formatBlocked(actors []ActorState) string {
	var blocked []string
	for _, current := range actors {
		if current.Blocked != "" {
			blocked = append(blocked, current.Name+": "+current.Blocked)
		}
	}
	return strings.Join(blocked, ", ")
}
