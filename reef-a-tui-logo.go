package main

// reef-a-tui-logo.go — bit-generated reference of the v0.17.5 logo.
//
// Regen:  bit -font fivebyfive -scale 0 -gradient '#FFFFFF' -direction down "Reef-A-TUI"
//
// The colour gradient at runtime is applied by Python (see
// DR_freshinstall.py::_LOGO_COLORS) so this .go is reference only.

import "fmt"

func main() {
	lines := []string{
		"████████    ██████████  ██████████  ██████████            ██████            ██████████  ██      ██  ██████",
		"██      ██  ██          ██          ██                  ██      ██              ██      ██      ██    ██  ",
		"████████    ████████    ████████    ████████    ██████  ██████████  ██████      ██      ██      ██    ██  ",
		"██    ██    ██          ██          ██                  ██      ██              ██      ██      ██    ██  ",
		"██      ██  ██████████  ██████████  ██                  ██      ██              ██        ██████    ██████",
	}
	for _, line := range lines {
		fmt.Println(line)
	}
}
