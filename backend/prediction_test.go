package main

import (
	"math"
	"testing"
)

func floatEquals(a, b float64) bool {
	return math.Abs(a-b) < 0.001
}

func TestComputeBudgetAlert(t *testing.T) {
	cases := []struct {
		name                        string
		budget, spent               float64
		daysElapsed, daysInMonth    int
		wantProjected, wantOverage  float64
		wantOverBudget              bool
	}{
		{
			name: "on pace under budget",
			budget: 1000, spent: 450, daysElapsed: 15, daysInMonth: 30,
			wantProjected: 900, wantOverage: 0, wantOverBudget: false,
		},
		{
			name: "projected to exceed budget",
			budget: 1000, spent: 600, daysElapsed: 15, daysInMonth: 30,
			wantProjected: 1200, wantOverage: 200, wantOverBudget: true,
		},
		{
			name: "exact budget match is not over",
			budget: 1000, spent: 500, daysElapsed: 15, daysInMonth: 30,
			wantProjected: 1000, wantOverage: 0, wantOverBudget: false,
		},
		{
			name: "zero days elapsed means zero projection",
			budget: 1000, spent: 0, daysElapsed: 0, daysInMonth: 30,
			wantProjected: 0, wantOverage: 0, wantOverBudget: false,
		},
		{
			name: "unset budget (0) never reports over budget",
			budget: 0, spent: 50, daysElapsed: 10, daysInMonth: 30,
			wantProjected: 150, wantOverage: 0, wantOverBudget: false,
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := computeBudgetAlert(c.budget, c.spent, c.daysElapsed, c.daysInMonth)
			if !floatEquals(got.ProjectedTotal, c.wantProjected) {
				t.Errorf("ProjectedTotal: got %v, want %v", got.ProjectedTotal, c.wantProjected)
			}
			if !floatEquals(got.ProjectedOverage, c.wantOverage) {
				t.Errorf("ProjectedOverage: got %v, want %v", got.ProjectedOverage, c.wantOverage)
			}
			if got.OverBudget != c.wantOverBudget {
				t.Errorf("OverBudget: got %v, want %v", got.OverBudget, c.wantOverBudget)
			}
		})
	}
}

func TestComputeForecast(t *testing.T) {
	input := map[string][]float64{
		"Food":      {100, 200, 300}, // avg 200
		"Transport": {50},            // avg 50
		"Empty":     {},              // no history -> omitted
	}
	got := computeForecast(input)

	byCategory := map[string]float64{}
	for _, f := range got {
		byCategory[f.Category] = f.PredictedAmount
	}

	if len(got) != 2 {
		t.Fatalf("expected 2 forecast entries (Empty omitted), got %d: %+v", len(got), got)
	}
	if !floatEquals(byCategory["Food"], 200) {
		t.Errorf("Food forecast: got %v, want 200", byCategory["Food"])
	}
	if !floatEquals(byCategory["Transport"], 50) {
		t.Errorf("Transport forecast: got %v, want 50", byCategory["Transport"])
	}
	if _, ok := byCategory["Empty"]; ok {
		t.Errorf("Empty category should be omitted from forecast, got %v", byCategory["Empty"])
	}
}

// Go randomises map iteration order, so an unsorted forecast made the dashboard
// bars reshuffle on every reload.
func TestComputeForecast_StableOrder(t *testing.T) {
	input := map[string][]float64{
		"Food": {300}, "Transport": {100}, "Bills": {200},
		"Health": {100}, "Shopping": {50}, "Other": {400},
	}
	want := []string{"Other", "Food", "Bills", "Health", "Transport", "Shopping"}

	for run := range 20 {
		got := computeForecast(input)
		for i, name := range want {
			if got[i].Category != name {
				t.Fatalf("run %d: position %d is %q, want %q (full order %+v)", run, i, got[i].Category, name, got)
			}
		}
	}
}
