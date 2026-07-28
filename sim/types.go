package sim

import "fmt"

type Point struct {
	X, Y int
}

type RoomType int

const (
	RoomTypeMain RoomType = iota
	RoomTypeInput
	RoomTypeOutput
	RoomTypeDisplay
)

type Room struct {
	MinX, MinY int
	MaxX, MaxY int
	Type       RoomType
}

type Display struct {
	Room          *Room
	Width, Height int
	Cursor        int
	Current       []int64
	Next          []int64
	Frames        [][]int64
}

func (r Room) Contains(p Point) bool {
	return p.X >= r.MinX && p.X <= r.MaxX && p.Y >= r.MinY && p.Y <= r.MaxY
}

func (r Room) IsOnBorder(p Point) bool {
	if !r.Contains(p) {
		return false
	}
	return p.X == r.MinX || p.X == r.MaxX || p.Y == r.MinY || p.Y == r.MaxY
}

type Pipe struct {
	// The path of the pipe, from the source cell adjacent to the room border,
	// to the destination cell adjacent to the destination room border.
	Path []Point

	// Values currently in the pipe. Length matches Path.
	// nil means empty.
	Values []*int64

	SourceRoom *Room
	DestRoom   *Room

	// The segment on the source room border where this pipe is attached.
	SourceSegment Point

	// The segment on the destination room border where this pipe is attached.
	DestSegment Point
}

type LittleMan struct {
	ID       int
	X, Y     int
	DX, DY   int
	A, B     int64
	BP       int64
	BornTick int
	Halted   bool
	Blocked  bool
}

type Program struct {
	Width, Height int
	Grid          [][]byte
	Rooms         []*Room
	Displays      []*Display
	Pipes         []*Pipe
	Men           []*LittleMan
	Literals      []*Literal
	InputQueue    []int64
	OutputQueue   []int64
	TickCount     int
	MaxTicks      int
	NextManID     int
	Error         error
	Halted        bool

	GridValues     map[Point]*int64
	NextPipeCell   map[Point]Point
	PipeCellsOrder []Point
}

func (p *Program) GetPipeVal(pt Point) *int64 {
	if p.GridValues == nil {
		return nil
	}
	return p.GridValues[pt]
}

func (p *Program) SetPipeVal(pt Point, val *int64) {
	if p.GridValues == nil {
		p.GridValues = make(map[Point]*int64)
	}
	p.GridValues[pt] = val
	for _, pipe := range p.Pipes {
		for i, pathPt := range pipe.Path {
			if pathPt == pt {
				pipe.Values[i] = val
			}
		}
	}
}

func (p *Program) GetAt(pt Point) byte {
	if pt.X < 0 || pt.Y < 0 || pt.X >= p.Width || pt.Y >= p.Height {
		return ' '
	}
	return p.Grid[pt.Y][pt.X]
}

func (p *Program) SetError(err error) {
	if p.Error == nil {
		p.Error = err
	}
}

func (p *Program) HaltError(msg string) {
	p.SetError(fmt.Errorf("%s", msg))
	p.Halted = true
}

type Literal struct {
	Min, Max     Point
	IsHorizontal bool
	ValForward   int64
	ValBackward  int64
	ErrForward   string
	ErrBackward  string
}
