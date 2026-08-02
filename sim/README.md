# Go Simulator 🧍‍♂️

`sim` is the basic test workbench for Little Man programs. It keeps the machine model explicit and inspectable, making it useful for validating generated `.man` files and debugging individual rooms.

For fast execution and profiling, it was succeeded by [Simulacrum](../simulacrum/README.md).

The module contains several CLI tools:
- `cmd/simulator` runs `.man` programs.
- `cmd/benchmark` runs test suites from [`public_tests`](../public_tests).
- `cmd/tester` runs the tests embedded in [`.block`](../blocks) files.
- `cmd/trace` prints machine state on each tick and extracts room topology.

100% vibe coded. Nothing to see here.
