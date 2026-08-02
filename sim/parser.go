package sim

import (
	"fmt"
	"strconv"
	"strings"
)

func ParseProgram(code string) (*Program, error) {
	lines := strings.Split(strings.TrimRight(code, " \t\r\n"), "\n")
	height := len(lines)
	width := 0
	for _, l := range lines {
		l = strings.TrimRight(l, "\r")
		if len(l) > width {
			width = len(l)
		}
	}

	p := &Program{
		Width:       width,
		Height:      height,
		Grid:        make([][]byte, height),
		InputQueue:  make([]int64, 0),
		OutputQueue: make([]int64, 0),
	}

	for y, l := range lines {
		l = strings.TrimRight(l, "\r")
		row := make([]byte, width)
		for x := 0; x < width; x++ {
			if x < len(l) {
				row[x] = l[x]
			} else {
				row[x] = ' '
			}
		}
		p.Grid[y] = row
	}

	if err := parseRooms(p); err != nil {
		return nil, err
	}

	if err := parseLiterals(p); err != nil {
		return nil, err
	}

	if err := parsePipes(p); err != nil {
		return nil, err
	}

	if err := spawnMen(p); err != nil {
		return nil, err
	}

	return p, nil
}

func parseLiterals(p *Program) error {
	// Parse horizontal literals.
	for y := 0; y < p.Height; y++ {
		startX := -1
		for x := 0; x < p.Width; x++ {
			if p.Grid[y][x] != '`' {
				continue
			}
			if startX == -1 {
				startX = x
				continue
			}

			forward := ""
			for i := startX + 1; i < x; i++ {
				value := p.Grid[y][i]
				if value != ' ' && (value < '0' || value > '9') {
					return fmt.Errorf(
						"expected a digit or a space between backticks, but found %q at (%d, %d)",
						value, i, y,
					)
				}
				if value != ' ' {
					forward += string(value)
				}
			}
			backward := reverseLiteral(forward)
			forwardValue, err := strconv.ParseInt(forward, 10, 64)
			forwardError := literalParseError(forward, err)
			backwardValue, err := strconv.ParseInt(backward, 10, 64)
			backwardError := literalParseError(backward, err)

			p.Literals = append(p.Literals, &Literal{
				Min:          Point{startX, y},
				Max:          Point{x, y},
				IsHorizontal: true,
				ValForward:   forwardValue,
				ValBackward:  backwardValue,
				ErrForward:   forwardError,
				ErrBackward:  backwardError,
			})
			startX = -1
		}
	}

	// Parse vertical literals.
	for x := 0; x < p.Width; x++ {
		startY := -1
		for y := 0; y < p.Height; y++ {
			if p.Grid[y][x] != '`' {
				continue
			}
			if startY == -1 {
				startY = y
				continue
			}

			forward := ""
			for i := startY + 1; i < y; i++ {
				value := p.Grid[i][x]
				if value != ' ' && (value < '0' || value > '9') {
					return fmt.Errorf(
						"expected a digit or a space between backticks, but found %q at (%d, %d)",
						value, x, i,
					)
				}
				if value != ' ' {
					forward += string(value)
				}
			}
			backward := reverseLiteral(forward)
			forwardValue, err := strconv.ParseInt(forward, 10, 64)
			forwardError := literalParseError(forward, err)
			backwardValue, err := strconv.ParseInt(backward, 10, 64)
			backwardError := literalParseError(backward, err)

			p.Literals = append(p.Literals, &Literal{
				Min:          Point{x, startY},
				Max:          Point{x, y},
				IsHorizontal: false,
				ValForward:   forwardValue,
				ValBackward:  backwardValue,
				ErrForward:   forwardError,
				ErrBackward:  backwardError,
			})
			startY = -1
		}
	}

	return nil
}

func reverseLiteral(value string) string {
	reversed := make([]byte, len(value))
	for i := range value {
		reversed[len(value)-1-i] = value[i]
	}
	return string(reversed)
}

func literalParseError(spelling string, err error) string {
	if err == nil {
		return ""
	}
	return fmt.Sprintf("invalid numeric literal %q: %v", spelling, err)
}

func parseRooms(p *Program) error {
	visited := make(map[Point]bool)
	for y := 0; y < p.Height; y++ {
		for x := 0; x < p.Width; x++ {
			if p.Grid[y][x] == '+' && !visited[Point{x, y}] {
				if display, ok, err := parseDisplayAt(p, x, y); err != nil {
					return err
				} else if ok {
					room := display.Room
					for px := room.MinX; px <= room.MaxX; px++ {
						visited[Point{px, room.MinY}] = true
						visited[Point{px, room.MaxY}] = true
					}
					for py := room.MinY; py <= room.MaxY; py++ {
						visited[Point{room.MinX, py}] = true
						visited[Point{room.MaxX, py}] = true
					}
					p.Rooms = append(p.Rooms, room)
					p.Displays = append(p.Displays, display)
					continue
				}
				// find width
				w := 1
				for x+w < p.Width && p.Grid[y][x+w] == '-' {
					w++
				}
				if x+w >= p.Width || p.Grid[y][x+w] != '+' {
					continue
				}
				// find height
				h := 1
				for y+h < p.Height && p.Grid[y+h][x] == '|' {
					h++
				}
				if y+h >= p.Height || p.Grid[y+h][x] != '+' {
					continue
				}
				// check if it's a valid rectangle
				valid := true
				for i := 1; i < w; i++ {
					if p.Grid[y+h][x+i] != '-' {
						valid = false
						break
					}
				}
				for i := 1; i < h; i++ {
					if p.Grid[y+i][x+w] != '|' {
						valid = false
						break
					}
				}
				if p.Grid[y+h][x+w] != '+' {
					valid = false
				}
				if valid {
					for i := 0; i <= w; i++ {
						visited[Point{x + i, y}] = true
						visited[Point{x + i, y + h}] = true
					}
					for i := 0; i <= h; i++ {
						visited[Point{x, y + i}] = true
						visited[Point{x + w, y + i}] = true
					}

					room := &Room{
						MinX: x, MinY: y,
						MaxX: x + w, MaxY: y + h,
						Type: RoomTypeMain,
					}
					for ry := y + 1; ry < y+h; ry++ {
						for rx := x + 1; rx < x+w; rx++ {
							if p.Grid[ry][rx] == 'I' {
								room.Type = RoomTypeInput
							} else if p.Grid[ry][rx] == 'O' {
								room.Type = RoomTypeOutput
							}
						}
					}
					p.Rooms = append(p.Rooms, room)
				}
			}
		}
	}
	return nil
}

func parseDisplayAt(p *Program, x, y int) (*Display, bool, error) {
	w := 1
	for x+w < p.Width && p.Grid[y][x+w] == '=' {
		w++
	}
	if w == 1 || x+w >= p.Width || p.Grid[y][x+w] != '+' {
		return nil, false, nil
	}
	h := 1
	for y+h < p.Height && p.Grid[y+h][x] == ':' {
		h++
	}
	if h == 1 || y+h >= p.Height || p.Grid[y+h][x] != '+' {
		return nil, false, nil
	}
	if w-1 > 64 || h-1 > 64 {
		return nil, false, fmt.Errorf("display at %d,%d exceeds 64x64", x, y)
	}
	for px := x + 1; px < x+w; px++ {
		if p.Grid[y+h][px] != '=' {
			return nil, false, fmt.Errorf("invalid display bottom wall at %d,%d", px, y+h)
		}
	}
	for py := y + 1; py < y+h; py++ {
		if p.Grid[py][x+w] != ':' {
			return nil, false, fmt.Errorf("invalid display right wall at %d,%d", x+w, py)
		}
	}
	if p.Grid[y+h][x+w] != '+' {
		return nil, false, fmt.Errorf("invalid display corner at %d,%d", x+w, y+h)
	}
	width, height := w-1, h-1
	room := &Room{
		MinX: x, MinY: y,
		MaxX: x + w, MaxY: y + h,
		Type: RoomTypeDisplay,
	}
	return &Display{
		Room:    room,
		Width:   width,
		Height:  height,
		Current: make([]int64, width*height),
		Next:    make([]int64, width*height),
	}, true, nil
}

func parsePipes(p *Program) error {
	dirs := []Point{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}
	arrowChars := map[Point]byte{{1, 0}: '>', {-1, 0}: '<', {0, 1}: 'v', {0, -1}: '^'}

	for _, room := range p.Rooms {
		for y := room.MinY; y <= room.MaxY; y++ {
			for x := room.MinX; x <= room.MaxX; x++ {
				if !room.IsOnBorder(Point{x, y}) {
					continue
				}
				borderPt := Point{x, y}

				for _, dir := range dirs {
					pipePt := Point{x + dir.X, y + dir.Y}
					if pipePt.X < 0 || pipePt.Y < 0 || pipePt.X >= p.Width || pipePt.Y >= p.Height {
						continue
					}

					if room.Contains(pipePt) {
						continue
					}

					arrow := p.Grid[pipePt.Y][pipePt.X]
					if arrow == arrowChars[dir] || (arrow == 'V' && dir.Y == 1) {
						if err := tracePipe(p, room, borderPt, pipePt, dir); err != nil {
							return err
						}
					}
				}
			}
		}
	}

	var realPipes []*Pipe
	for _, pB := range p.Pipes {
		isGhost := false
		for _, pA := range p.Pipes {
			if pA == pB {
				continue
			}
			for i := 1; i < len(pA.Path); i++ {
				if pA.Path[i] == pB.Path[0] {
					isGhost = true
					break
				}
			}
			if isGhost {
				break
			}
		}
		if !isGhost {
			realPipes = append(realPipes, pB)
		}
	}
	p.Pipes = realPipes
	for _, display := range p.Displays {
		sideCount := make(map[string]int)
		for _, pipe := range p.Pipes {
			if pipe.DestRoom != display.Room {
				continue
			}
			side, err := displayPipeSide(display.Room, pipe.DestSegment)
			if err != nil {
				return err
			}
			sideCount[side]++
			if sideCount[side] > 1 {
				return fmt.Errorf("display has multiple %s pipes", side)
			}
		}
	}

	p.GridValues = make(map[Point]*int64)
	p.NextPipeCell = make(map[Point]Point)
	var cellOrder []Point
	visited := make(map[Point]bool)
	for _, pipe := range p.Pipes {
		for i := len(pipe.Path) - 1; i >= 0; i-- {
			pt := pipe.Path[i]
			if i < len(pipe.Path)-1 {
				p.NextPipeCell[pt] = pipe.Path[i+1]
			}
			if !visited[pt] {
				visited[pt] = true
				cellOrder = append(cellOrder, pt)
			}
			if pipe.Values[i] != nil {
				p.GridValues[pt] = pipe.Values[i]
			}
		}
	}
	p.PipeCellsOrder = cellOrder

	return nil
}

func displayPipeSide(room *Room, point Point) (string, error) {
	if point.X == room.MinX || point.X == room.MaxX {
		if point.Y == room.MinY || point.Y == room.MaxY {
			return "", fmt.Errorf("pipe attached to display corner at %v", point)
		}
		if point.X == room.MaxX {
			return "", fmt.Errorf("pipe attached to right side of display at %v", point)
		}
		return "data", nil
	}
	if point.Y == room.MinY {
		return "addr", nil
	}
	if point.Y == room.MaxY {
		return "swap", nil
	}
	return "", fmt.Errorf("pipe has invalid display attachment at %v", point)
}

func getArrowDir(c byte) (Point, bool) {
	switch c {
	case '>':
		return Point{1, 0}, true
	case '<':
		return Point{-1, 0}, true
	case '^':
		return Point{0, -1}, true
	case 'v', 'V':
		return Point{0, 1}, true
	}
	return Point{}, false
}

func getRoomAt(p *Program, pt Point) *Room {
	for _, r := range p.Rooms {
		if r.Contains(pt) {
			return r
		}
	}
	return nil
}

func tracePipe(p *Program, srcRoom *Room, srcSegment Point, startCell Point, startDir Point) error {
	curr := startCell
	dir := startDir
	path := []Point{curr}

	for {
		nextCell := Point{curr.X + dir.X, curr.Y + dir.Y}

		destRoom := getRoomAt(p, nextCell)
		if destRoom != nil {
			if !destRoom.IsOnBorder(nextCell) {
				return fmt.Errorf("pipe entering room not on border")
			}

			_, isArrow := getArrowDir(p.GetAt(curr))
			if !isArrow {
				return fmt.Errorf("pipe must end with an arrowhead")
			}

			if len(path) < 2 {
				return nil
			}

			pipe := &Pipe{
				Path:          path,
				Values:        make([]*int64, len(path)),
				SourceRoom:    srcRoom,
				DestRoom:      destRoom,
				SourceSegment: srcSegment,
				DestSegment:   nextCell,
			}
			p.Pipes = append(p.Pipes, pipe)
			return nil
		}

		curr = nextCell
		char := p.GetAt(curr)
		if char == ' ' {
			return fmt.Errorf("broken pipe at %v", curr)
		}

		if newDir, isArrow := getArrowDir(char); isArrow {
			if newDir.X == -dir.X && newDir.Y == -dir.Y {
				return fmt.Errorf("arrowhead pointing back at %v", curr)
			}
			dir = newDir
		} else if char == '-' {
			if dir.Y != 0 {
				return fmt.Errorf("vertical flow through '-' at %v", curr)
			}
		} else if char == '|' {
			if dir.X != 0 {
				return fmt.Errorf("horizontal flow through '|' at %v", curr)
			}
		} else {
			return fmt.Errorf("invalid pipe character '%c' at %v", char, curr)
		}

		path = append(path, curr)
	}
}

func spawnMen(p *Program) error {
	id := 0
	for _, room := range p.Rooms {
		if room.Type == RoomTypeDisplay {
			continue
		}
		for y := room.MinY + 1; y < room.MaxY; y++ {
			for x := room.MinX + 1; x < room.MaxX; x++ {
				if p.Grid[y][x] == '@' {
					p.Men = append(p.Men, &LittleMan{
						ID: id,
						X:  x, Y: y,
						DX: 1, DY: 0,
					})
					id++
				}
			}
		}
	}
	if len(p.Men) == 0 {
		return fmt.Errorf("no little men found")
	}
	p.NextManID = id
	return nil
}
