package main

import (
	"fmt"
	"strconv"
)

func parseLiterals(p *Program) error {
	// Parse horizontal
	for y := 0; y < p.Height; y++ {
		startX := -1
		for x := 0; x < p.Width; x++ {
			if p.Grid[y][x] == '`' {
				if startX == -1 {
					startX = x
				} else {
					fwdStr := ""
					for i := startX + 1; i < x; i++ {
						value := p.Grid[y][i]
						if value != ' ' && (value < '0' || value > '9') {
							return fmt.Errorf(
								"expected a digit or a space between backticks, but found %q at (%d, %d)",
								value, i, y,
							)
						}
						if value != ' ' {
							fwdStr += string(value)
						}
					}
					backStr := ""
					for i := len(fwdStr) - 1; i >= 0; i-- {
						backStr += string(fwdStr[i])
					}

					fVal, err := strconv.ParseInt(fwdStr, 10, 64)
					fErr := literalParseError(fwdStr, err)
					bVal, err := strconv.ParseInt(backStr, 10, 64)
					bErr := literalParseError(backStr, err)

					p.Literals = append(p.Literals, &Literal{
						Min:          Point{startX, y},
						Max:          Point{x, y},
						IsHorizontal: true,
						ValForward:   fVal,
						ValBackward:  bVal,
						ErrForward:   fErr,
						ErrBackward:  bErr,
					})
					startX = -1
				}
			}
		}
	}

	// Parse vertical
	for x := 0; x < p.Width; x++ {
		startY := -1
		for y := 0; y < p.Height; y++ {
			if p.Grid[y][x] == '`' {
				if startY == -1 {
					startY = y
				} else {
					fwdStr := ""
					for i := startY + 1; i < y; i++ {
						value := p.Grid[i][x]
						if value != ' ' && (value < '0' || value > '9') {
							return fmt.Errorf(
								"expected a digit or a space between backticks, but found %q at (%d, %d)",
								value, x, i,
							)
						}
						if value != ' ' {
							fwdStr += string(value)
						}
					}
					backStr := ""
					for i := len(fwdStr) - 1; i >= 0; i-- {
						backStr += string(fwdStr[i])
					}

					fVal, err := strconv.ParseInt(fwdStr, 10, 64)
					fErr := literalParseError(fwdStr, err)
					bVal, err := strconv.ParseInt(backStr, 10, 64)
					bErr := literalParseError(backStr, err)

					p.Literals = append(p.Literals, &Literal{
						Min:          Point{x, startY},
						Max:          Point{x, y},
						IsHorizontal: false,
						ValForward:   fVal,
						ValBackward:  bVal,
						ErrForward:   fErr,
						ErrBackward:  bErr,
					})
					startY = -1
				}
			}
		}
	}

	return nil
}

func literalParseError(spelling string, err error) string {
	if err == nil {
		return ""
	}
	return fmt.Sprintf("invalid numeric literal %q: %v", spelling, err)
}

func handleLiteral(p *Program, m *LittleMan, pt Point) bool {
	var movingHoriz bool
	if m.DX != 0 {
		movingHoriz = true
	} else if m.DY != 0 {
		movingHoriz = false
	} else {
		return false
	}

	var relevantLit *Literal
	for _, l := range p.Literals {
		if l.IsHorizontal == movingHoriz {
			if l.IsHorizontal {
				if pt.Y == l.Min.Y && pt.X >= l.Min.X && pt.X <= l.Max.X {
					relevantLit = l
					break
				}
			} else {
				if pt.X == l.Min.X && pt.Y >= l.Min.Y && pt.Y <= l.Max.Y {
					relevantLit = l
					break
				}
			}
		}
	}

	if relevantLit == nil {
		if p.GetAt(pt) == '`' {
			return true // no-op
		}
		return false // normal execution
	}

	isOpen := false
	if movingHoriz {
		if m.DX > 0 && pt.X == relevantLit.Min.X {
			isOpen = true
			if relevantLit.ErrForward == "" {
				m.A = relevantLit.ValForward
			} else {
				p.HaltError(relevantLit.ErrForward)
			}
		} else if m.DX < 0 && pt.X == relevantLit.Max.X {
			isOpen = true
			if relevantLit.ErrBackward == "" {
				m.A = relevantLit.ValBackward
			} else {
				p.HaltError(relevantLit.ErrBackward)
			}
		}
	} else {
		if m.DY > 0 && pt.Y == relevantLit.Min.Y {
			isOpen = true
			if relevantLit.ErrForward == "" {
				m.A = relevantLit.ValForward
			} else {
				p.HaltError(relevantLit.ErrForward)
			}
		} else if m.DY < 0 && pt.Y == relevantLit.Max.Y {
			isOpen = true
			if relevantLit.ErrBackward == "" {
				m.A = relevantLit.ValBackward
			} else {
				p.HaltError(relevantLit.ErrBackward)
			}
		}
	}

	_ = isOpen // just for logging if needed
	return true
}
