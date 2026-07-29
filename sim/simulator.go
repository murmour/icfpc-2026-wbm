package sim

import (
	"fmt"
)

const maxLiveMen = 65536

func abs(a int) int {
	if a < 0 {
		return -a
	}
	return a
}

func dist(a, b Point) int {
	return abs(a.X-b.X) + abs(a.Y-b.Y)
}

func handleLiteral(p *Program, m *LittleMan, pt Point) bool {
	movingHorizontal := m.DX != 0
	if !movingHorizontal && m.DY == 0 {
		return false
	}

	var literal *Literal
	for _, candidate := range p.Literals {
		if candidate.IsHorizontal != movingHorizontal {
			continue
		}
		if candidate.IsHorizontal {
			if pt.Y == candidate.Min.Y && pt.X >= candidate.Min.X && pt.X <= candidate.Max.X {
				literal = candidate
				break
			}
		} else if pt.X == candidate.Min.X && pt.Y >= candidate.Min.Y && pt.Y <= candidate.Max.Y {
			literal = candidate
			break
		}
	}

	if literal == nil {
		if p.GetAt(pt) == '`' {
			return true
		}
		return false
	}

	if movingHorizontal {
		if m.DX > 0 && pt.X == literal.Min.X {
			if literal.ErrForward == "" {
				m.A = literal.ValForward
			} else {
				p.HaltError(literal.ErrForward)
			}
		} else if m.DX < 0 && pt.X == literal.Max.X {
			if literal.ErrBackward == "" {
				m.A = literal.ValBackward
			} else {
				p.HaltError(literal.ErrBackward)
			}
		}
	} else if m.DY > 0 && pt.Y == literal.Min.Y {
		if literal.ErrForward == "" {
			m.A = literal.ValForward
		} else {
			p.HaltError(literal.ErrForward)
		}
	} else if m.DY < 0 && pt.Y == literal.Max.Y {
		if literal.ErrBackward == "" {
			m.A = literal.ValBackward
		} else {
			p.HaltError(literal.ErrBackward)
		}
	}

	return true
}

func (p *Program) getOutgoingPipes(room *Room) []*Pipe {
	var pipes []*Pipe
	for _, pipe := range p.Pipes {
		if pipe.SourceRoom == room {
			pipes = append(pipes, pipe)
		}
	}
	return pipes
}

func (p *Program) getIncomingPipes(room *Room) []*Pipe {
	var pipes []*Pipe
	for _, pipe := range p.Pipes {
		if pipe.DestRoom == room {
			pipes = append(pipes, pipe)
		}
	}
	return pipes
}

func (p *Program) nearestOutgoing(room *Room, pt Point) *Pipe {
	pipes := p.getOutgoingPipes(room)
	if len(pipes) == 0 {
		return nil
	}
	best := pipes[0]
	bestSeg := best.Path[0]
	for _, pipe := range pipes[1:] {
		seg := pipe.Path[0]
		d1, d2 := dist(pt, bestSeg), dist(pt, seg)
		if d2 < d1 || (d2 == d1 && (seg.Y < bestSeg.Y || (seg.Y == bestSeg.Y && seg.X < bestSeg.X))) {
			best = pipe
			bestSeg = seg
		}
	}
	return best
}

func (p *Program) nearestIncoming(room *Room, pt Point) *Pipe {
	pipes := p.getIncomingPipes(room)
	if len(pipes) == 0 {
		return nil
	}
	best := pipes[0]
	bestSeg := best.Path[len(best.Path)-1]
	for _, pipe := range pipes[1:] {
		seg := pipe.Path[len(pipe.Path)-1]
		d1, d2 := dist(pt, bestSeg), dist(pt, seg)
		if d2 < d1 || (d2 == d1 && (seg.Y < bestSeg.Y || (seg.Y == bestSeg.Y && seg.X < bestSeg.X))) {
			best = pipe
			bestSeg = seg
		} else if d2 == d1 && seg == bestSeg {
			if best.Values[len(best.Path)-1] == nil && pipe.Values[len(pipe.Path)-1] != nil {
				best = pipe
			}
		}
	}
	return best
}

func (p *Program) nextManID() int {
	if p.NextManID == 0 {
		for _, man := range p.Men {
			if man.ID >= p.NextManID {
				p.NextManID = man.ID + 1
			}
		}
	}
	id := p.NextManID
	p.NextManID++
	return id
}

func (p *Program) splitMan(index int, man *LittleMan, room *Room) {
	leftDX, leftDY := man.DY, -man.DX
	rightDX, rightDY := -man.DY, man.DX
	if (leftDX == 0 && leftDY == 0) || room == nil {
		p.HaltError(fmt.Sprintf("little man %d split with an invalid heading", man.ID))
		return
	}

	leftPoint := Point{X: man.X + leftDX, Y: man.Y + leftDY}
	rightPoint := Point{X: man.X + rightDX, Y: man.Y + rightDY}
	for _, birthPoint := range []Point{rightPoint, leftPoint} {
		birthRoom := getRoomAt(p, birthPoint)
		if birthRoom != room || room.IsOnBorder(birthPoint) {
			p.HaltError(fmt.Sprintf(
				"little man %d split into a wall at %d,%d",
				man.ID,
				birthPoint.X,
				birthPoint.Y,
			))
			return
		}
	}

	liveMen := 0
	for _, candidate := range p.Men {
		if !candidate.Halted {
			liveMen++
		}
	}
	if liveMen+1 > maxLiveMen {
		p.HaltError(fmt.Sprintf("split exceeded the live little man limit of %d", maxLiveMen))
		return
	}

	makeCopy := func(point Point, dx, dy int) *LittleMan {
		return &LittleMan{
			ID:       p.nextManID(),
			X:        point.X,
			Y:        point.Y,
			DX:       dx,
			DY:       dy,
			A:        man.A,
			B:        man.B,
			BP:       man.BP,
			BornTick: p.TickCount,
		}
	}

	right := makeCopy(rightPoint, rightDX, rightDY)
	left := makeCopy(leftPoint, leftDX, leftDY)
	man.Halted = true

	collideAtBirth := func(born *LittleMan) {
		for _, occupant := range p.Men {
			if occupant == man || occupant.Halted {
				continue
			}
			if occupant.X == born.X && occupant.Y == born.Y {
				occupant.Halted = true
				born.Halted = true
			}
		}
	}

	// The right copy inherits the original man's execution-order slot.
	collideAtBirth(right)
	p.Men[index] = right

	// The left copy is newest and therefore executes after every existing man.
	collideAtBirth(left)
	p.Men = append(p.Men, left)
}

func (p *Program) Step() {
	if p.Halted || p.Error != nil {
		return
	}
	p.TickCount++

	if p.GridValues == nil {
		p.GridValues = make(map[Point]*int64)
	}
	for _, pipe := range p.Pipes {
		for i, pt := range pipe.Path {
			if pipe.Values[i] != nil {
				p.GridValues[pt] = pipe.Values[i]
			}
		}
	}

	// 1. Pipes shift
	for _, curr := range p.PipeCellsOrder {
		next, hasNext := p.NextPipeCell[curr]
		if hasNext {
			if p.GridValues[next] == nil && p.GridValues[curr] != nil {
				p.SetPipeVal(next, p.GridValues[curr])
				p.SetPipeVal(curr, nil)
			}
		}
	}

	// 2. I/O
	var outputRoom *Room
	var inputRoom *Room
	for _, r := range p.Rooms {
		if r.Type == RoomTypeOutput {
			outputRoom = r
		} else if r.Type == RoomTypeInput {
			inputRoom = r
		}
	}

	if outputRoom != nil {
		for _, pipe := range p.getIncomingPipes(outputRoom) {
			lastIdx := len(pipe.Path) - 1
			pt := pipe.Path[lastIdx]
			if p.GridValues[pt] != nil {
				val := *p.GridValues[pt]
				p.OutputQueue = append(p.OutputQueue, val)
				p.SetPipeVal(pt, nil)
			}
		}
	}

	if inputRoom != nil && len(p.InputQueue) > 0 {
		for _, pipe := range p.getOutgoingPipes(inputRoom) {
			pt := pipe.Path[0]
			if p.GridValues[pt] == nil {
				val := p.InputQueue[0]
				p.InputQueue = p.InputQueue[1:]
				p.SetPipeVal(pt, &val)
				// only read one input per tick according to "the next value is placed"
				break
			}
		}
	}

	for _, display := range p.Displays {
		if err := p.stepDisplay(display); err != nil {
			p.HaltError(err.Error())
			return
		}
	}

	// 3. Execution. Men born by Y this tick are appended/replaced but are not
	// included in this tick's execution set.
	executingMen := len(p.Men)
	for manIndex := 0; manIndex < executingMen; manIndex++ {
		m := p.Men[manIndex]
		if m.Halted {
			continue
		}

		pt := Point{m.X, m.Y}
		if handleLiteral(p, m, pt) {
			continue
		}
		char := p.GetAt(pt)
		room := getRoomAt(p, Point{m.X, m.Y})

		// Unblock flag
		unblocked := true

		switch char {
		case '@', '.', ' ':
			// nop
		case 'Y':
			p.splitMan(manIndex, m, room)
			if p.Error != nil {
				return
			}
			continue
		case 'H':
			m.Halted = true
		case 'M':
			m.B = m.A
		case 'W':
			m.A, m.B = m.B, m.A
		case '+':
			m.A = m.A + m.B
		case '-':
			m.A = m.A - m.B
		case '*':
			m.A = m.A * m.B
		case '%':
			if m.B == 0 {
				m.A = 0
			} else {
				m.A = m.A % m.B
				// handle sign matching B
				if (m.A < 0 && m.B > 0) || (m.A > 0 && m.B < 0) {
					m.A += m.B
				}
			}
		case '/':
			if m.B == 0 {
				m.A = 0
			} else {
				// floored division
				q := m.A / m.B
				r := m.A % m.B
				if (m.A < 0) != (m.B < 0) && r != 0 {
					q--
					r += m.B
				}
				m.A = q
				m.B = r
			}
		case 'N':
			m.A = -m.A
		case '&':
			m.A = m.A & m.B
		case '|':
			m.A = m.A | m.B
		case '~':
			m.A = m.A ^ m.B
		case '{':
			if m.B < 0 || m.B > 63 {
				m.A = 0
			} else {
				m.A = m.A << m.B
			}
		case '}':
			if m.B < 0 {
				m.A = 0
			} else if m.B > 63 {
				if m.A < 0 {
					m.A = -1
				} else {
					m.A = 0
				}
			} else {
				m.A = m.A >> m.B
			}
		case '>':
			m.DX, m.DY = 1, 0
		case '<':
			m.DX, m.DY = -1, 0
		case '^':
			m.DX, m.DY = 0, -1
		case 'v', 'V':
			m.DX, m.DY = 0, 1
		case 'X':
			if m.A > 0 { // clockwise
				m.DX, m.DY = -m.DY, m.DX
			} else if m.A < 0 { // counter-clockwise
				m.DX, m.DY = m.DY, -m.DX
			}
		case 'b':
			m.BP = m.A
		case 'm':
			m.BP--
		case 'd':
			if m.BP > 0 { // clockwise
				m.DX, m.DY = -m.DY, m.DX
			}
		case 'a':
			if m.BP > 0 { // counter-clockwise
				m.DX, m.DY = m.DY, -m.DX
			}
		case 'q':
			pipe := p.nearestIncoming(room, Point{m.X, m.Y})
			if pipe == nil {
				p.HaltError("q executed with no incoming pipe")
				return
			}
			count := int64(0)
			for _, pt := range pipe.Path {
				if p.GridValues[pt] != nil {
					count++
				}
			}
			m.BP = count
		case ']':
			m.BP = m.BP >> 1
		case 'x':
			if m.BP&1 == 1 { // clockwise
				m.DX, m.DY = -m.DY, m.DX
			} else {
				m.DX, m.DY = m.DY, -m.DX
			}
		case 's':
			pipe := p.nearestOutgoing(room, Point{m.X, m.Y})
			if pipe == nil {
				p.HaltError("s executed with no outgoing pipe")
				return
			}
			pt := pipe.Path[0]
			if p.GridValues[pt] == nil {
				v := m.A
				p.SetPipeVal(pt, &v)
			} else {
				unblocked = false
			}
		case 'S':
			pipes := p.getOutgoingPipes(room)
			if len(pipes) == 0 {
				p.HaltError("S executed with no outgoing pipes")
				return
			}
			allFree := true
			for _, pipe := range pipes {
				if p.GridValues[pipe.Path[0]] != nil {
					allFree = false
					break
				}
			}
			if allFree {
				for _, pipe := range pipes {
					v := m.A
					p.SetPipeVal(pipe.Path[0], &v)
				}
			} else {
				unblocked = false
			}
		case 'r':
			pipe := p.nearestIncoming(room, Point{m.X, m.Y})
			if pipe == nil {
				p.HaltError(fmt.Sprintf("r executed with no incoming pipe at {%d, %d}", m.X, m.Y))
				return
			}
			lastIdx := len(pipe.Path) - 1
			pt := pipe.Path[lastIdx]
			if p.GridValues[pt] != nil {
				m.A = *p.GridValues[pt]
				p.SetPipeVal(pt, nil)
			} else {
				unblocked = false
			}
		case 'R', 'U':
			pipes := p.getIncomingPipes(room)
			if len(pipes) == 0 {
				p.HaltError(fmt.Sprintf("%c executed with no incoming pipe at {%d, %d}", char, m.X, m.Y))
				return
			}
			var readyPipe *Pipe
			var readySeg Point
			for _, pipe := range pipes {
				lastIdx := len(pipe.Path) - 1
				pt := pipe.Path[lastIdx]
				if p.GridValues[pt] != nil {
					seg := pt
					if readyPipe == nil {
						readyPipe = pipe
						readySeg = seg
					} else {
						d1, d2 := dist(Point{m.X, m.Y}, readySeg), dist(Point{m.X, m.Y}, seg)
						if d2 < d1 || (d2 == d1 && (seg.Y < readySeg.Y || (seg.Y == readySeg.Y && seg.X < readySeg.X))) {
							readyPipe = pipe
							readySeg = seg
						}
					}
				}
			}
			if readyPipe != nil {
				lastIdx := len(readyPipe.Path) - 1
				pt := readyPipe.Path[lastIdx]
				m.A = *p.GridValues[pt]
				p.SetPipeVal(pt, nil)
				if char == 'U' { // turn away
					dx := m.X - readySeg.X
					dy := m.Y - readySeg.Y
					if dx != 0 {
						dx = dx / abs(dx)
						m.DX, m.DY = dx, 0
					} else if dy != 0 {
						dy = dy / abs(dy)
						m.DX, m.DY = 0, dy
					}
				}
			} else {
				unblocked = false
			}
		default:
			if char >= '0' && char <= '9' {
				m.A = int64(char - '0')
			} else {
				// Need to handle numeric literals between backticks?
				// The spec says they are parsed as literal. For simplicity, we just handle single digits here.
				// If the test case has full literals, we should implement it. But let's keep it simple for now.
				p.HaltError(fmt.Sprintf("unsupported instruction '%c' at %v", char, Point{m.X, m.Y}))
				return
			}
		}

		m.Blocked = !unblocked
	}

	// 4. Movement
	oldPositions := make(map[*LittleMan]Point)
	for _, m := range p.Men {
		if !m.Halted && !m.Blocked && m.BornTick < p.TickCount {
			oldPositions[m] = Point{X: m.X, Y: m.Y}
			m.X += m.DX
			m.Y += m.DY

			room := getRoomAt(p, Point{m.X, m.Y})
			if room == nil || room.IsOnBorder(Point{m.X, m.Y}) {
				p.HaltError(fmt.Sprintf("little man %d hit a wall at %d,%d", m.ID, m.X, m.Y))
				return
			}
		}
	}

	// Resolve all same-cell and position-swap collisions simultaneously.
	var activeMen []*LittleMan
	for _, man := range p.Men {
		if !man.Halted {
			activeMen = append(activeMen, man)
		}
	}
	collided := make(map[*LittleMan]bool)
	for i, first := range activeMen {
		for _, second := range activeMen[i+1:] {
			sameCell := first.X == second.X && first.Y == second.Y
			firstOld, firstMoved := oldPositions[first]
			secondOld, secondMoved := oldPositions[second]
			swapped := firstMoved && secondMoved &&
				first.X == secondOld.X && first.Y == secondOld.Y &&
				second.X == firstOld.X && second.Y == firstOld.Y
			if sameCell || swapped {
				collided[first] = true
				collided[second] = true
			}
		}
	}
	for man := range collided {
		man.Halted = true
	}

	// Check if all halted
	allHalted := true
	for _, m := range p.Men {
		if !m.Halted {
			allHalted = false
			break
		}
	}
	if allHalted {
		p.Halted = true
	}

	if p.TickCount >= p.MaxTicks {
		p.Halted = true
		p.SetError(fmt.Errorf("step cap reached"))
	}
}

func (p *Program) stepDisplay(display *Display) error {
	inputs := make(map[string]*Pipe)
	for _, pipe := range p.getIncomingPipes(display.Room) {
		side, err := displayPipeSide(display.Room, pipe.DestSegment)
		if err != nil {
			return err
		}
		inputs[side] = pipe
	}
	consume := func(side string) *int64 {
		pipe := inputs[side]
		if pipe == nil {
			return nil
		}
		point := pipe.Path[len(pipe.Path)-1]
		value := p.GridValues[point]
		if value != nil {
			p.SetPipeVal(point, nil)
		}
		return value
	}

	if value := consume("addr"); value != nil {
		if *value < 0 || *value >= int64(len(display.Next)) {
			return fmt.Errorf("display address %d is outside 0..%d", *value, len(display.Next)-1)
		}
		display.Cursor = int(*value)
	}
	if value := consume("data"); value != nil {
		if *value < 0 || *value > 15 {
			return fmt.Errorf("display color %d is outside 0..15", *value)
		}
		display.Next[display.Cursor] = *value
		display.Cursor = (display.Cursor + 1) % len(display.Next)
	}
	if value := consume("swap"); value != nil {
		if *value != 0 && *value != 1 {
			return fmt.Errorf("display swap %d is not 0 or 1", *value)
		}
		copy(display.Current, display.Next)
		display.Frames = append(display.Frames, append([]int64(nil), display.Current...))
		if *value == 0 {
			clear(display.Next)
			display.Cursor = 0
		}
	}
	return nil
}
