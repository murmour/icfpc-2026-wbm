// Command folding_go is the fast placement and orthogonal-routing kernel.
package main

import (
	"container/heap"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"math/rand"
	"os"
	"sort"
)

type Point struct {
	X int `json:"x"`
	Y int `json:"y"`
}
type Port struct {
	Name, Side string
	Offset     int
	Flow       string
	TieRank    int `json:"tie_rank"`
}
type Rect struct{ Left, Top, Right, Bottom int }
type Constraint struct {
	Type     string   `json:"type"`
	Point    Point    `json:"point"`
	Region   Rect     `json:"region"`
	Port     string   `json:"port"`
	Headings []string `json:"headings"`
}
type Rule struct {
	Kind    string  `json:"kind"`
	Turn    *string `json:"turn"`
	Heading *string `json:"heading"`
	Port    *string `json:"port"`
}
type Exit struct {
	Name string
	Rule Rule
}
type Node struct {
	Name, Kind, Instruction string
	Exits                   []Exit
	Constraints             []Constraint
}
type Action struct{ Code string }
type Edge struct {
	Name         string `json:"name"`
	Source       string `json:"source"`
	SourceExit   string `json:"source_exit"`
	Target       string `json:"target"`
	Actions      []Action
	MinimumSteps int     `json:"minimum_steps"`
	MaximumSteps *int    `json:"maximum_steps"`
	Expected     float64 `json:"expected_traversals"`
}
type Room struct {
	Width, Height int
	Ports         []Port
	Obstacles     []Point
}
type Graph struct {
	Name  string
	Room  Room
	Nodes []Node
	Edges []Edge
	Start string
}
type Pose struct {
	Node     string `json:"node"`
	Point    Point  `json:"point"`
	Incoming string `json:"incoming"`
}
type Input struct {
	Graph   Graph  `json:"graph"`
	Initial []Pose `json:"initial_poses"`
}
type Route struct {
	Edge   string  `json:"edge"`
	Points []Point `json:"points"`
}
type ActionPlacement struct {
	Edge        string  `json:"edge"`
	ActionIndex int     `json:"action_index"`
	Points      []Point `json:"points"`
}
type Output struct {
	Nodes     []Pose            `json:"nodes"`
	Routes    []Route           `json:"routes"`
	Actions   []ActionPlacement `json:"actions"`
	Unrouted  []string          `json:"unrouted_edges,omitempty"`
	EdgeOrder []string          `json:"edge_order,omitempty"`
}

const (
	North = "north"
	East  = "east"
	South = "south"
	West  = "west"
)

var headings = []string{North, East, South, West}
var vectors = map[string]Point{North: {0, -1}, East: {1, 0}, South: {0, 1}, West: {-1, 0}}

func add(a, b Point) Point     { return Point{a.X + b.X, a.Y + b.Y} }
func manhattan(a, b Point) int { return abs(a.X-b.X) + abs(a.Y-b.Y) }
func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}
func opposite(h string) string {
	return map[string]string{North: South, South: North, East: West, West: East}[h]
}
func turn(h, t string) string {
	i := 0
	for j, v := range headings {
		if v == h {
			i = j
		}
	}
	d := map[string]int{"straight": 0, "left": -1, "right": 1}[t]
	return headings[(i+d+4)%4]
}

type placer struct {
	g              Graph
	nodes          map[string]Node
	edges          map[string]Edge
	ports          map[string]Port
	obstacles      map[Point]bool
	rng            *rand.Rand
	heightWeight   float64
	longEdgeWeight float64
	expansionLimit int
	priority       map[string]bool
}

func newPlacer(g Graph, seed int64, hw, longEdgeWeight float64, expansionLimit int, priority map[string]bool) *placer {
	p := &placer{g: g, nodes: map[string]Node{}, edges: map[string]Edge{}, ports: map[string]Port{}, obstacles: map[Point]bool{}, rng: rand.New(rand.NewSource(seed)), heightWeight: hw, longEdgeWeight: longEdgeWeight, expansionLimit: expansionLimit, priority: priority}
	for _, n := range g.Nodes {
		p.nodes[n.Name] = n
	}
	for _, e := range g.Edges {
		p.edges[e.Name] = e
	}
	for _, x := range g.Room.Ports {
		p.ports[x.Name] = x
	}
	for _, x := range g.Room.Obstacles {
		p.obstacles[x] = true
	}
	return p
}
func (p *placer) inside(q Point) bool {
	return q.X >= 0 && q.X < p.g.Room.Width && q.Y >= 0 && q.Y < p.g.Room.Height && !p.obstacles[q]
}
func boundary(room Room, port Port) Point {
	switch port.Side {
	case North:
		return Point{port.Offset, -1}
	case South:
		return Point{port.Offset, room.Height}
	case West:
		return Point{-1, port.Offset}
	default:
		return Point{room.Width, port.Offset}
	}
}
func (p *placer) selected(q Point, flow string) Port {
	var best Port
	bd := math.MaxInt
	for _, x := range p.g.Room.Ports {
		if x.Flow != flow {
			continue
		}
		d := manhattan(q, boundary(p.g.Room, x))
		if d < bd || d == bd && x.TieRank < best.TieRank {
			best = x
			bd = d
		}
	}
	return best
}
func contains(r Rect, q Point) bool {
	return q.X >= r.Left && q.X <= r.Right && q.Y >= r.Top && q.Y <= r.Bottom
}
func has(ss []string, s string) bool {
	for _, v := range ss {
		if v == s {
			return true
		}
	}
	return false
}
func (p *placer) valid(n Node, pose Pose) bool {
	if !p.inside(pose.Point) {
		return false
	}
	if n.Kind == "start" && pose.Incoming != East {
		return false
	}
	for _, c := range n.Constraints {
		switch c.Type {
		case "FixedAt":
			if pose.Point != c.Point {
				return false
			}
		case "Within":
			if !contains(c.Region, pose.Point) {
				return false
			}
		case "NearestPort":
			target := p.ports[c.Port]
			if p.selected(pose.Point, target.Flow).Name != target.Name {
				return false
			}
		case "AllowedIncoming":
			if !has(c.Headings, pose.Incoming) {
				return false
			}
		}
	}
	return true
}
func copyPoses(src map[string]Pose) map[string]Pose {
	r := make(map[string]Pose, len(src))
	for k, v := range src {
		r[k] = v
	}
	return r
}
func (p *placer) randomValid(n Node, incoming string, maxY int) Pose {
	for tries := 0; tries < 20000; tries++ {
		q := Point{p.rng.Intn(p.g.Room.Width), p.rng.Intn(max(1, min(p.g.Room.Height, maxY+1)))}
		x := Pose{n.Name, q, incoming}
		if p.valid(n, x) {
			return x
		}
	}
	for y := 0; y < p.g.Room.Height; y++ {
		for x := 0; x < p.g.Room.Width; x++ {
			v := Pose{n.Name, Point{x, y}, incoming}
			if p.valid(n, v) {
				return v
			}
		}
	}
	panic("empty domain " + n.Name)
}
func (p *placer) coarse(poses map[string]Pose) (int, float64, float64, int) {
	hard := 0
	occupied := map[Point]bool{}
	maxY := 0
	for _, n := range p.g.Nodes {
		x := poses[n.Name]
		if !p.valid(n, x) {
			hard++
		}
		if occupied[x.Point] {
			hard++
		}
		occupied[x.Point] = true
		if x.Point.Y > maxY {
			maxY = x.Point.Y
		}
	}
	w := 0.0
	for _, e := range p.g.Edges {
		d := max(manhattan(poses[e.Source].Point, poses[e.Target].Point), e.MinimumSteps)
		w += float64(d)*e.Expected + p.longEdgePenalty(d)
	}
	return hard, float64(hard)*1e9 + w + p.heightWeight*float64(maxY+1), w, maxY + 1
}
func (p *placer) longEdgePenalty(steps int) float64 {
	excess := max(0, steps-24)
	return p.longEdgeWeight * float64(excess*excess)
}
func temperature(i, n int) float64 {
	if n <= 1 {
		return .02
	}
	x := float64(i) / float64(n-1)
	return 4 * math.Pow(.02/4, x)
}
func (p *placer) mutate(src map[string]Pose, focus []string) map[string]Pose {
	r := copyPoses(src)
	var n Node
	if len(focus) > 0 && p.rng.Float64() < .75 {
		n = p.nodes[focus[p.rng.Intn(len(focus))]]
	} else {
		n = p.g.Nodes[p.rng.Intn(len(p.g.Nodes))]
	}
	old := r[n.Name]
	if n.Kind != "start" && p.rng.Float64() < .18 {
		for {
			h := headings[p.rng.Intn(4)]
			x := Pose{n.Name, old.Point, h}
			if h != old.Incoming && p.valid(n, x) {
				r[n.Name] = x
				return r
			}
		}
	}
	if p.rng.Float64() < .72 {
		for k := 0; k < 100; k++ {
			q := Point{old.Point.X + p.rng.Intn(17) - 8, old.Point.Y + p.rng.Intn(17) - 10}
			x := Pose{n.Name, q, old.Incoming}
			if p.valid(n, x) {
				r[n.Name] = x
				return r
			}
		}
	}
	_, _, _, height := p.coarse(src)
	r[n.Name] = p.randomValid(n, old.Incoming, height)
	return r
}
func (p *placer) mutateFailed(src map[string]Pose, failed []string) map[string]Pose {
	if len(failed) == 0 {
		return p.mutate(src, nil)
	}
	edge := p.edges[failed[p.rng.Intn(len(failed))]]
	moving, anchor := edge.Source, edge.Target
	if p.rng.Intn(2) == 0 {
		moving, anchor = anchor, moving
	}
	node := p.nodes[moving]
	old := src[moving]
	center := src[anchor].Point
	span := edge.MinimumSteps + len(edge.Actions) + 8
	span = min(24, max(8, span))
	for tries := 0; tries < 200; tries++ {
		q := Point{center.X + p.rng.Intn(2*span+1) - span, center.Y + p.rng.Intn(2*span+1) - span}
		pose := Pose{moving, q, old.Incoming}
		if p.valid(node, pose) {
			out := copyPoses(src)
			out[moving] = pose
			return out
		}
	}
	return p.mutate(src, []string{edge.Source, edge.Target})
}
func occupiedBy(poses map[string]Pose, point Point, except ...string) string {
	for name, pose := range poses {
		skip := false
		for _, excluded := range except {
			if name == excluded {
				skip = true
				break
			}
		}
		if !skip && pose.Point == point {
			return name
		}
	}
	return ""
}
func (p *placer) relocateBlocker(src map[string]Pose, name string, avoid Point) (map[string]Pose, bool) {
	node, old := p.nodes[name], src[name]
	_, _, _, height := p.coarse(src)
	for tries := 0; tries < 300; tries++ {
		q := Point{old.Point.X + p.rng.Intn(33) - 16, old.Point.Y + p.rng.Intn(33) - 16}
		if tries > 200 {
			q = Point{p.rng.Intn(p.g.Room.Width), p.rng.Intn(max(1, height))}
		}
		pose := Pose{name, q, old.Incoming}
		if manhattan(q, avoid) >= 4 && occupiedBy(src, q, name) == "" && p.valid(node, pose) {
			out := copyPoses(src)
			out[name] = pose
			return out, true
		}
	}
	return src, false
}
func (p *placer) mutateRepair(src map[string]Pose, failed []string) map[string]Pose {
	if len(failed) == 0 {
		return p.mutate(src, nil)
	}
	edge := p.edges[failed[p.rng.Intn(len(failed))]]
	source, target := src[edge.Source], src[edge.Target]
	depart := p.departure(source, p.findExit(p.nodes[edge.Source], edge.SourceExit))
	first := add(source.Point, vectors[depart])
	beforeTarget := Point{target.Point.X - vectors[target.Incoming].X, target.Point.Y - vectors[target.Incoming].Y}
	if !p.inside(first) {
		if out, ok := p.relocateBlocker(src, edge.Source, first); ok {
			return out
		}
	}
	if !p.inside(beforeTarget) {
		if out, ok := p.relocateBlocker(src, edge.Target, beforeTarget); ok {
			return out
		}
	}
	for _, required := range []Point{first, beforeTarget} {
		if blocker := occupiedBy(src, required, edge.Source, edge.Target); blocker != "" {
			if out, ok := p.relocateBlocker(src, blocker, required); ok {
				return out
			}
		}
	}
	moving, anchor := edge.Source, edge.Target
	if p.rng.Intn(2) == 0 {
		moving, anchor = anchor, moving
	}
	node, old := p.nodes[moving], src[moving]
	center := src[anchor].Point
	needed := edge.MinimumSteps + len(edge.Actions) + 4
	span := min(28, max(10, needed+8))
	for tries := 0; tries < 300; tries++ {
		q := Point{center.X + p.rng.Intn(2*span+1) - span, center.Y + p.rng.Intn(2*span+1) - span}
		distance := manhattan(q, center)
		pose := Pose{moving, q, old.Incoming}
		if distance >= needed && distance <= needed+12 && occupiedBy(src, q, moving) == "" && p.valid(node, pose) {
			out := copyPoses(src)
			out[moving] = pose
			return out
		}
	}
	return p.mutateFailed(src, failed)
}
func accept(cur, next, temp float64, r *rand.Rand) bool {
	return next <= cur || r.Float64() < math.Exp((cur-next)/temp)
}

func (p *placer) departure(pose Pose, exit Exit) string {
	r := exit.Rule
	switch r.Kind {
	case "turn":
		return turn(pose.Incoming, *r.Turn)
	case "absolute":
		return *r.Heading
	default:
		port := p.ports[*r.Port]
		return map[string]string{North: South, South: North, East: West, West: East}[port.Side]
	}
}
func (p *placer) findExit(node Node, name string) Exit {
	for _, x := range node.Exits {
		if x.Name == name {
			return x
		}
	}
	panic("missing exit")
}

type reservation struct {
	Arrow  string
	Action bool
}
type state struct {
	P     Point
	H     string
	Phase int
}
type item struct {
	S              state
	Cost, Priority float64
	Steps, Serial  int
	Index          int
}
type queue []*item

func (q queue) Len() int { return len(q) }
func (q queue) Less(i, j int) bool {
	if q[i].Priority == q[j].Priority {
		return q[i].Serial < q[j].Serial
	}
	return q[i].Priority < q[j].Priority
}
func (q queue) Swap(i, j int) { q[i], q[j] = q[j], q[i]; q[i].Index = i; q[j].Index = j }
func (q *queue) Push(x any)   { v := x.(*item); v.Index = len(*q); *q = append(*q, v) }
func (q *queue) Pop() any     { o := *q; n := len(o); v := o[n-1]; *q = o[:n-1]; return v }

type parent struct {
	Prev state
	Has  bool
}

func (p *placer) routeOne(e Edge, start, goal Point, depart, arrival string, blocked map[Point]bool, res map[Point]reservation) ([]Point, bool) {
	first := add(start, vectors[depart])
	if !p.inside(first) || blocked[first] || res[first].Action || (first == goal && arrival != depart) {
		return nil, false
	}
	if first == goal {
		return []Point{start, goal}, e.MinimumSteps <= 1
	}
	q := &queue{}
	heap.Init(q)
	serial := 0
	s0 := state{first, depart, min(1, e.MinimumSteps)}
	heap.Push(q, &item{S: s0, Cost: 1, Priority: 1 + float64(manhattan(first, goal)), Steps: 1})
	costs := map[state]float64{s0: 1}
	parents := map[state]parent{s0: {}}
	stepsBy := map[state]int{s0: 1}
	var end state
	found := false
	for q.Len() > 0 && serial < p.expansionLimit {
		it := heap.Pop(q).(*item)
		if costs[it.S] != it.Cost {
			continue
		}
		serial++
		if it.S.P == goal {
			if it.S.H == arrival && it.Steps >= e.MinimumSteps {
				end = it.S
				found = true
				break
			}
			continue
		}
		for _, nh := range headings {
			if nh == opposite(it.S.H) {
				continue
			}
			if rr, ok := res[it.S.P]; ok {
				if rr.Action {
					continue
				}
				if rr.Arrow != "" && nh != rr.Arrow {
					continue
				}
				if rr.Arrow == "" && nh != it.S.H {
					continue
				}
			}
			nb := add(it.S.P, vectors[nh])
			if !p.inside(nb) || blocked[nb] || res[nb].Action || nb == start {
				continue
			}
			if nb == goal && nh != arrival {
				continue
			}
			ns := it.Steps + 1
			if ns < e.MinimumSteps && nb == goal {
				continue
			}
			if e.MaximumSteps != nil && ns > *e.MaximumSteps {
				continue
			}
			nc := it.Cost + 1
			if nh != it.S.H {
				nc += .2
			}
			st := state{nb, nh, min(ns, e.MinimumSteps)}
			old, ok := costs[st]
			if ok && nc >= old {
				continue
			}
			costs[st] = nc
			parents[st] = parent{it.S, true}
			stepsBy[st] = ns
			heap.Push(q, &item{S: st, Cost: nc, Priority: nc + float64(manhattan(nb, goal)), Steps: ns, Serial: serial})
		}
	}
	if !found {
		return nil, false
	}
	rev := []Point{end.P}
	cur := end
	for parents[cur].Has {
		cur = parents[cur].Prev
		rev = append(rev, cur.P)
	}
	rev = append(rev, start)
	path := make([]Point, len(rev))
	for i := range rev {
		path[len(rev)-1-i] = rev[i]
	}
	return path, true
}
func headingBetween(a, b Point) string {
	d := Point{b.X - a.X, b.Y - a.Y}
	for h, v := range vectors {
		if d == v {
			return h
		}
	}
	panic("nonadjacent")
}
func countBends(path []Point) int {
	n := 0
	last := ""
	for i := 1; i < len(path); i++ {
		h := headingBetween(path[i-1], path[i])
		if last != "" && h != last {
			n++
		}
		last = h
	}
	return n
}
func placeActions(e Edge, path []Point, res map[Point]reservation) ([]ActionPlacement, bool) {
	if len(e.Actions) == 0 {
		return nil, true
	}
	hs := make([]string, len(path)-1)
	for i := range hs {
		hs[i] = headingBetween(path[i], path[i+1])
	}
	bends := map[int]bool{}
	for i := 1; i < len(path)-1; i++ {
		if hs[i-1] != hs[i] {
			bends[i] = true
		}
	}
	out := []ActionPlacement{}
	cursor := 1
	for ai, a := range e.Actions {
		l := len(a.Code)
		var pts []Point
		for cursor+l <= len(path)-1 {
			ok := true
			h := ""
			for j := cursor; j < cursor+l; j++ {
				if _, occupied := res[path[j]]; bends[j] || occupied {
					ok = false
					break
				}
				if j == cursor {
					h = hs[j-1]
				}
				if hs[j-1] != h || hs[j] != h {
					ok = false
					break
				}
			}
			if ok {
				pts = append([]Point(nil), path[cursor:cursor+l]...)
				break
			}
			cursor++
		}
		if pts == nil {
			return nil, false
		}
		out = append(out, ActionPlacement{e.Name, ai, pts})
		cursor += l
	}
	return out, true
}
func simplePath(path []Point) bool {
	seen := map[Point]bool{}
	for _, point := range path {
		if seen[point] {
			return false
		}
		seen[point] = true
	}
	return true
}
func (p *placer) routeEdge(e Edge, start, goal Point, depart, arrival string, blocked map[Point]bool, res map[Point]reservation) ([]Point, []ActionPlacement, bool) {
	lastMinimum := e.MinimumSteps
	if len(e.Actions) > 0 {
		lastMinimum += 2*len(e.Actions) + 8
	}
	if e.MaximumSteps != nil && lastMinimum > *e.MaximumSteps {
		lastMinimum = *e.MaximumSteps
	}
	for required := e.MinimumSteps; required <= lastMinimum; required++ {
		trial := e
		trial.MinimumSteps = required
		path, ok := p.routeOne(trial, start, goal, depart, arrival, blocked, res)
		if !ok || !simplePath(path) {
			continue
		}
		acts, ok := placeActions(e, path, res)
		if ok {
			return path, acts, true
		}
	}
	return nil, nil, false
}
func reserve(path []Point, acts []ActionPlacement, res map[Point]reservation) {
	ac := map[Point]bool{}
	for _, a := range acts {
		for _, q := range a.Points {
			ac[q] = true
		}
	}
	hs := make([]string, len(path)-1)
	for i := range hs {
		hs[i] = headingBetween(path[i], path[i+1])
	}
	for i := 1; i < len(path)-1; i++ {
		q := path[i]
		if ac[q] {
			res[q] = reservation{Action: true}
			continue
		}
		arrow := ""
		if hs[i-1] != hs[i] {
			arrow = hs[i]
		}
		if _, ok := res[q]; !ok {
			res[q] = reservation{Arrow: arrow}
		}
	}
}

type routing struct {
	Routes      []Route
	Actions     []ActionPlacement
	Failed      []string
	Weighted    float64
	LongPenalty float64
	Bends       int
}

func (p *placer) weightedOrder() []string {
	order := append([]Edge(nil), p.g.Edges...)
	p.rng.Shuffle(len(order), func(i, j int) { order[i], order[j] = order[j], order[i] })
	sort.SliceStable(order, func(i, j int) bool {
		return order[i].Expected > order[j].Expected
	})
	names := make([]string, len(order))
	for i, edge := range order {
		names[i] = edge.Name
	}
	return names
}
func (p *placer) orderFromOutput(out Output) []string {
	if len(out.EdgeOrder) > 0 {
		return append([]string(nil), out.EdgeOrder...)
	}
	order := make([]string, 0, len(p.g.Edges))
	for _, route := range out.Routes {
		order = append(order, route.Edge)
	}
	order = append(order, out.Unrouted...)
	return order
}
func (p *placer) mutateOrder(src, failed []string) []string {
	order := append([]string(nil), src...)
	if len(order) < 3 {
		return order
	}
	const firstMutable = 1
	if len(failed) > 0 && p.rng.Float64() < 0.65 {
		name := failed[p.rng.Intn(len(failed))]
		from := -1
		for i, edge := range order {
			if edge == name {
				from = i
				break
			}
		}
		if from > firstMutable {
			to := firstMutable + p.rng.Intn(from-firstMutable)
			copy(order[to+1:from+1], order[to:from])
			order[to] = name
			return order
		}
	}
	count := len(order) - firstMutable
	from := firstMutable + p.rng.Intn(count)
	to := firstMutable + p.rng.Intn(count)
	if from == to {
		to = firstMutable + (to-firstMutable+1)%count
	}
	name := order[from]
	if from < to {
		copy(order[from:to], order[from+1:to+1])
	} else {
		copy(order[to+1:from+1], order[to:from])
	}
	order[to] = name
	return order
}
func (p *placer) routeAll(poses map[string]Pose, names []string) routing {
	order := make([]Edge, 0, len(p.g.Edges))
	seen := map[string]bool{}
	for _, name := range names {
		if edge, ok := p.edges[name]; ok && !seen[name] {
			order = append(order, edge)
			seen[name] = true
		}
	}
	for _, edge := range p.g.Edges {
		if !seen[edge.Name] {
			order = append(order, edge)
		}
	}
	nodes := map[Point]bool{}
	for _, x := range poses {
		nodes[x.Point] = true
	}
	res := map[Point]reservation{}
	out := routing{}
	for _, e := range order {
		src, tgt := poses[e.Source], poses[e.Target]
		blocked := map[Point]bool{}
		for q := range p.obstacles {
			blocked[q] = true
		}
		for q := range nodes {
			if q != src.Point && q != tgt.Point {
				blocked[q] = true
			}
		}
		path, acts, ok := p.routeEdge(e, src.Point, tgt.Point, p.departure(src, p.findExit(p.nodes[e.Source], e.SourceExit)), tgt.Incoming, blocked, res)
		if !ok {
			out.Failed = append(out.Failed, e.Name)
			continue
		}
		out.Routes = append(out.Routes, Route{e.Name, path})
		out.Actions = append(out.Actions, acts...)
		reserve(path, acts, res)
		out.Weighted += float64(len(path)-1) * e.Expected
		out.LongPenalty += p.longEdgePenalty(len(path) - 1)
		out.Bends += countBends(path)
	}
	return out
}
func (p *placer) routingFromOutput(out Output) routing {
	r := routing{Routes: out.Routes, Actions: out.Actions, Failed: out.Unrouted}
	for _, route := range out.Routes {
		e := p.edges[route.Edge]
		r.Weighted += float64(len(route.Points)-1) * e.Expected
		r.LongPenalty += p.longEdgePenalty(len(route.Points) - 1)
		r.Bends += countBends(route.Points)
	}
	return r
}
func (p *placer) failedWeight(r routing) float64 {
	total := 0.0
	for _, name := range r.Failed {
		total += p.edges[name].Expected
	}
	return total
}
func (p *placer) better(a, b routing) bool {
	af, ax, ac, ab := len(a.Failed), p.failedWeight(a), a.Weighted+a.LongPenalty, a.Bends
	bf, bx, bc, bb := len(b.Failed), p.failedWeight(b), b.Weighted+b.LongPenalty, b.Bends
	return af < bf || af == bf && (ax < bx || ax == bx && (ac < bc || ac == bc && ab < bb))
}
func (p *placer) routingEnergy(r routing) float64 {
	return float64(len(r.Failed))*4 + p.failedWeight(r)*0.2 + (r.Weighted+r.LongPenalty)/5000
}
func (p *placer) search(initial map[string]Pose, initialOrder []string, placementIters, routingIters int, baseline *routing) (map[string]Pose, routing, []string) {
	start := copyPoses(initial)
	startOrder := append([]string(nil), initialOrder...)
	cur := copyPoses(initial)
	_, ce, _, _ := p.coarse(cur)
	best := copyPoses(cur)
	bh, be, _, _ := p.coarse(best)
	for i := 0; i < placementIters; i++ {
		x := p.mutate(cur, nil)
		h, e, _, _ := p.coarse(x)
		if accept(ce, e, temperature(i, placementIters), p.rng) {
			cur = x
			ce = e
		}
		if h < bh || h == bh && e < be {
			best = x
			bh = h
			be = e
		}
	}
	cur = best
	curOrder := append([]string(nil), initialOrder...)
	r := p.routeAll(cur, curOrder)
	startRouting := p.routeAll(start, startOrder)
	if p.better(startRouting, r) {
		cur = start
		curOrder = startOrder
		r = startRouting
	}
	bestR := r
	best = copyPoses(cur)
	bestOrder := append([]string(nil), curOrder...)
	if baseline != nil && p.better(*baseline, bestR) {
		bestR = *baseline
		best = copyPoses(start)
		bestOrder = append([]string(nil), startOrder...)
	}
	energy := p.routingEnergy(r)
	for i := 0; i < routingIters; i++ {
		focus := []string{}
		for _, name := range r.Failed {
			e := p.edges[name]
			focus = append(focus, e.Source, e.Target)
		}
		x := copyPoses(cur)
		xOrder := append([]string(nil), curOrder...)
		if p.rng.Float64() < 0.30 {
			xOrder = p.mutateOrder(xOrder, r.Failed)
		} else {
			if len(r.Failed) > 0 {
				u := p.rng.Float64()
				if u < 0.5 {
					x = p.mutateRepair(cur, r.Failed)
				} else if u < 0.8 {
					x = p.mutateFailed(cur, r.Failed)
				} else {
					x = p.mutate(cur, focus)
				}
			} else {
				x = p.mutate(cur, focus)
			}
			if p.rng.Float64() < 0.15 {
				xOrder = p.mutateOrder(xOrder, r.Failed)
			}
		}
		h, _, _, _ := p.coarse(x)
		if h != 0 {
			continue
		}
		rr := p.routeAll(x, xOrder)
		ne := p.routingEnergy(rr)
		if accept(energy, ne, 3*temperature(i, routingIters), p.rng) {
			cur = x
			curOrder = xOrder
			r = rr
			energy = ne
		}
		if p.better(rr, bestR) {
			best = x
			bestR = rr
			bestOrder = append([]string(nil), xOrder...)
		}
	}
	return best, bestR, bestOrder
}
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func main() {
	input := flag.String("graph", "", "exported graph JSON")
	output := flag.String("output", "", "candidate JSON")
	initialFile := flag.String("initial", "", "previous candidate")
	seed := flag.Int64("seed", 0, "seed")
	pi := flag.Int("placement-iterations", 1000, "coarse iterations")
	ri := flag.Int("routing-iterations", 50, "route-aware iterations")
	scale := flag.Float64("scale-y", 1, "initial Y scale")
	hw := flag.Float64("height-weight", 20, "bounding height weight")
	longEdgeWeight := flag.Float64("long-edge-weight", 0.5, "quadratic penalty above 24 steps")
	expansionLimit := flag.Int("astar-expansions", 20000, "A* expansion limit per edge")
	probeEdge := flag.String("probe-edge", "", "diagnose one edge without route reservations")
	keepBaseline := flag.Bool("keep-baseline", true, "preserve the input candidate as a lower bound")
	flag.Parse()
	raw, err := os.ReadFile(*input)
	if err != nil {
		panic(err)
	}
	var in Input
	if err = json.Unmarshal(raw, &in); err != nil {
		panic(err)
	}
	initial := in.Initial
	priority := map[string]bool{}
	var baselineOutput *Output
	if *initialFile != "" {
		b, e := os.ReadFile(*initialFile)
		if e != nil {
			panic(e)
		}
		var old Output
		if e = json.Unmarshal(b, &old); e != nil {
			panic(e)
		}
		initial = old.Nodes
		for _, name := range old.Unrouted {
			priority[name] = true
		}
		baselineOutput = &old
	}
	poses := map[string]Pose{}
	for _, x := range initial {
		if *scale != 1 {
			x.Point.Y = int(math.Round(float64(x.Point.Y) * *scale))
		}
		poses[x.Node] = x
	}
	p := newPlacer(in.Graph, *seed, *hw, *longEdgeWeight, *expansionLimit, priority)
	if *probeEdge != "" {
		edge := p.edges[*probeEdge]
		src, tgt := poses[edge.Source], poses[edge.Target]
		blocked := map[Point]bool{}
		for point := range p.obstacles {
			blocked[point] = true
		}
		for _, pose := range poses {
			if pose.Point != src.Point && pose.Point != tgt.Point {
				blocked[pose.Point] = true
			}
		}
		path, actions, ok := p.routeEdge(edge, src.Point, tgt.Point, p.departure(src, p.findExit(p.nodes[edge.Source], edge.SourceExit)), tgt.Incoming, blocked, map[Point]reservation{})
		fmt.Printf("probe edge=%s ok=%v steps=%d actions=%d\n", edge.Name, ok, max(0, len(path)-1), len(actions))
		return
	}
	edgeOrder := p.weightedOrder()
	var baseline *routing
	if baselineOutput != nil {
		edgeOrder = p.orderFromOutput(*baselineOutput)
	}
	if baselineOutput != nil && *keepBaseline {
		r := p.routingFromOutput(*baselineOutput)
		baseline = &r
	}
	best, routing, bestOrder := p.search(poses, edgeOrder, *pi, *ri, baseline)
	nodes := make([]Pose, 0, len(in.Graph.Nodes))
	maxY := 0
	for _, n := range in.Graph.Nodes {
		x := best[n.Name]
		nodes = append(nodes, x)
		if x.Point.Y > maxY {
			maxY = x.Point.Y
		}
	}
	out := Output{Nodes: nodes, Routes: routing.Routes, Actions: routing.Actions, Unrouted: routing.Failed, EdgeOrder: bestOrder}
	encoded, _ := json.Marshal(out)
	if err = os.WriteFile(*output, encoded, 0644); err != nil {
		panic(err)
	}
	fmt.Printf("nodes=%d edges=%d unrouted=%d failed_weight=%.3f weighted=%.0f long_penalty=%.0f bends=%d used_height=%d\n", len(nodes), len(in.Graph.Edges), len(routing.Failed), p.failedWeight(routing), routing.Weighted, routing.LongPenalty, routing.Bends, maxY+1)
}
