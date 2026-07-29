package main

import (
	"database/sql"
	"path/filepath"
	"testing"
	"time"
)

func date(s string) time.Time {
	t, err := time.Parse("2006-01-02", s)
	if err != nil {
		panic(err)
	}
	return t
}

func TestComputeMonthSavings(t *testing.T) {
	cases := []struct {
		name           string
		income, spent  float64
		wantNet, wantRate float64
	}{
		{"kept a third", 3000, 2000, 1000, 33.333},
		{"spent every penny", 2000, 2000, 0, 0},
		{"overspent", 2000, 2500, -500, -25},
		// No income is not a savings rate of zero percent, it is no rate at
		// all — dividing by it would report minus infinity.
		{"no income recorded", 0, 500, -500, 0},
		{"nothing at all", 0, 0, 0, 0},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := computeMonthSavings("2026-07", c.income, c.spent)
			if !floatEquals(got.Net, c.wantNet) {
				t.Errorf("Net: got %v, want %v", got.Net, c.wantNet)
			}
			if !floatEquals(got.Rate, c.wantRate) {
				t.Errorf("Rate: got %v, want %v", got.Rate, c.wantRate)
			}
		})
	}
}

func TestComputeGoalProgress(t *testing.T) {
	goal := func(target float64, deadline string) Goal {
		return Goal{Name: "Emergency Fund", TargetAmount: target, TargetDate: deadline}
	}

	cases := []struct {
		name             string
		goal             Goal
		saved            float64
		observedPerMonth float64
		monthsLeft       int
		hasHistory       bool
		wantPace         string
		wantRequired     float64
		wantPercent      float64
		wantRemaining    float64
	}{
		{
			name: "funded fast enough to land in time",
			goal: goal(1000, "2026-12-31"), saved: 300, observedPerMonth: 200,
			monthsLeft: 5, hasHistory: true,
			wantPace: "ahead", wantRequired: 140, wantPercent: 30, wantRemaining: 700,
		},
		{
			name: "funded too slowly to land in time",
			goal: goal(1000, "2026-12-31"), saved: 300, observedPerMonth: 100,
			monthsLeft: 5, hasHistory: true,
			wantPace: "behind", wantRequired: 140, wantPercent: 30, wantRemaining: 700,
		},
		{
			name: "exactly on the required rate counts as ahead",
			goal: goal(1000, "2026-12-31"), saved: 300, observedPerMonth: 140,
			monthsLeft: 5, hasHistory: true,
			wantPace: "ahead", wantRequired: 140, wantPercent: 30, wantRemaining: 700,
		},
		{
			name: "deadline set but nothing contributed yet",
			goal: goal(1000, "2026-12-31"), saved: 0, observedPerMonth: 0,
			monthsLeft: 5, hasHistory: false,
			wantPace: "unknown", wantRequired: 200, wantPercent: 0, wantRemaining: 1000,
		},
		{
			// Saving without a deadline is legitimate; there is simply no pace
			// to be behind on, so it must not be reported as behind.
			name: "no deadline means no pace",
			goal: goal(1000, ""), saved: 300, observedPerMonth: 10,
			monthsLeft: -1, hasHistory: true,
			wantPace: "none", wantRequired: 0, wantPercent: 30, wantRemaining: 700,
		},
		{
			name: "target reached",
			goal: goal(1000, "2026-12-31"), saved: 1000, observedPerMonth: 500,
			monthsLeft: 5, hasHistory: true,
			wantPace: "complete", wantRequired: 0, wantPercent: 100, wantRemaining: 0,
		},
		{
			name: "over-saved caps at 100 percent and owes nothing",
			goal: goal(1000, "2026-12-31"), saved: 1400, observedPerMonth: 500,
			monthsLeft: 5, hasHistory: true,
			wantPace: "complete", wantRequired: 0, wantPercent: 100, wantRemaining: 0,
		},
		{
			name: "due this month owes the whole remainder",
			goal: goal(1000, "2026-07-31"), saved: 300, observedPerMonth: 500,
			monthsLeft: 0, hasHistory: true,
			wantPace: "behind", wantRequired: 700, wantPercent: 30, wantRemaining: 700,
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := computeGoalProgress(c.goal, c.saved, c.observedPerMonth, c.monthsLeft, c.hasHistory)
			if got.Pace != c.wantPace {
				t.Errorf("Pace: got %q, want %q", got.Pace, c.wantPace)
			}
			if !floatEquals(got.RequiredPerMonth, c.wantRequired) {
				t.Errorf("RequiredPerMonth: got %v, want %v", got.RequiredPerMonth, c.wantRequired)
			}
			if !floatEquals(got.PercentComplete, c.wantPercent) {
				t.Errorf("PercentComplete: got %v, want %v", got.PercentComplete, c.wantPercent)
			}
			if !floatEquals(got.Remaining, c.wantRemaining) {
				t.Errorf("Remaining: got %v, want %v", got.Remaining, c.wantRemaining)
			}
		})
	}
}

func TestMonthsUntil(t *testing.T) {
	now := date("2026-07-29")
	cases := []struct {
		name, target string
		want         int
	}{
		{"five months ahead", "2026-12-31", 5},
		{"same month", "2026-07-01", 0},
		{"already past clamps to zero", "2026-03-15", 0},
		{"across a year boundary", "2027-01-10", 6},
		{"no deadline", "", -1},
		{"unparseable date is treated as no deadline", "not-a-date", -1},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := monthsUntil(now, c.target); got != c.want {
				t.Errorf("monthsUntil(%q): got %d, want %d", c.target, got, c.want)
			}
		})
	}
}

func TestMonthsFunding(t *testing.T) {
	now := date("2026-07-29")
	cases := []struct {
		name, first string
		want        int
	}{
		{"first contribution this month", "2026-07-02", 1},
		{"three months of funding", "2026-05-20", 3},
		{"across a year boundary", "2025-08-01", 12},
		{"unparseable date divides by one", "", 1},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := monthsFunding(now, c.first); got != c.want {
				t.Errorf("monthsFunding(%q): got %d, want %d", c.first, got, c.want)
			}
		})
	}
}

// Subtracting a month from the 31st overflows into the wrong month, which
// produced duplicate entries in the savings history.
func TestLastMonths_EndOfMonthDoesNotOverflow(t *testing.T) {
	got := lastMonths(date("2026-03-31"), 6)
	want := []string{"2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"}

	if len(got) != len(want) {
		t.Fatalf("got %d months, want %d: %v", len(got), len(want), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("position %d: got %q, want %q (full: %v)", i, got[i], want[i], got)
		}
	}
}

func TestAverageRate_SkipsMonthsWithoutIncome(t *testing.T) {
	history := []MonthSavings{
		computeMonthSavings("2026-05", 1000, 500), // 50%
		computeMonthSavings("2026-06", 0, 400),    // no income, no rate
		computeMonthSavings("2026-07", 1000, 700), // 30%
	}
	// Counting the incomeless month would report 26.7% instead of 40%.
	if got := averageRate(history); !floatEquals(got, 40) {
		t.Errorf("averageRate: got %v, want 40", got)
	}
	if got := averageRate(nil); got != 0 {
		t.Errorf("averageRate of no history: got %v, want 0", got)
	}
}

// A database written before savings existed must gain the new column without
// losing the budget already in it.
func TestInitDB_UpgradesExistingDatabase(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "old.db")

	old, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("opening old db: %v", err)
	}
	if _, err := old.Exec(`CREATE TABLE settings (
		id             INTEGER PRIMARY KEY CHECK (id = 1),
		monthly_budget REAL NOT NULL DEFAULT 0
	)`); err != nil {
		t.Fatalf("creating old settings table: %v", err)
	}
	if _, err := old.Exec(`INSERT INTO settings (id, monthly_budget) VALUES (1, 1500)`); err != nil {
		t.Fatalf("seeding old settings: %v", err)
	}
	old.Close()

	db, err := InitDB(dbPath)
	if err != nil {
		t.Fatalf("InitDB on an existing database: %v", err)
	}
	defer db.Close()

	var budget, target float64
	if err := db.QueryRow("SELECT monthly_budget, savings_target FROM settings WHERE id = 1").Scan(&budget, &target); err != nil {
		t.Fatalf("querying upgraded settings: %v", err)
	}
	if budget != 1500 {
		t.Errorf("existing budget was lost: got %v, want 1500", budget)
	}
	if target != 0 {
		t.Errorf("savings_target should default to 0, got %v", target)
	}

	// Running it again must be a no-op rather than a duplicate-column failure.
	db2, err := InitDB(dbPath)
	if err != nil {
		t.Fatalf("second InitDB after upgrade: %v", err)
	}
	db2.Close()
}

// Contributions have no meaning without their goal, so the schema cascades.
func TestDeletingGoalRemovesContributions(t *testing.T) {
	db, err := InitDB(filepath.Join(t.TempDir(), "cascade.db"))
	if err != nil {
		t.Fatalf("InitDB: %v", err)
	}
	defer db.Close()

	res, err := db.Exec("INSERT INTO goals (name, target_amount, target_date) VALUES ('Laptop', 1800, '')")
	if err != nil {
		t.Fatalf("inserting goal: %v", err)
	}
	goalID, _ := res.LastInsertId()
	if _, err := db.Exec(
		"INSERT INTO contributions (goal_id, amount, date) VALUES (?, 200, '2026-07-01')", goalID,
	); err != nil {
		t.Fatalf("inserting contribution: %v", err)
	}

	if _, err := db.Exec("DELETE FROM goals WHERE id = ?", goalID); err != nil {
		t.Fatalf("deleting goal: %v", err)
	}

	var orphans int
	if err := db.QueryRow("SELECT COUNT(*) FROM contributions WHERE goal_id = ?", goalID).Scan(&orphans); err != nil {
		t.Fatalf("counting contributions: %v", err)
	}
	if orphans != 0 {
		t.Errorf("expected contributions to be removed with the goal, %d left behind", orphans)
	}
}

func TestLoadGoalProgress_UsesContributionHistory(t *testing.T) {
	db, err := InitDB(filepath.Join(t.TempDir(), "goals.db"))
	if err != nil {
		t.Fatalf("InitDB: %v", err)
	}
	defer db.Close()

	if _, err := db.Exec(
		"INSERT INTO goals (name, target_amount, target_date) VALUES ('Emergency Fund', 5000, '2026-12-31')",
	); err != nil {
		t.Fatalf("inserting goal: %v", err)
	}
	// A goal with no contributions at all must still appear, at zero.
	if _, err := db.Exec("INSERT INTO goals (name, target_amount, target_date) VALUES ('Camera', 900, '')"); err != nil {
		t.Fatalf("inserting second goal: %v", err)
	}
	for _, d := range []string{"2026-05-01", "2026-06-01", "2026-07-01"} {
		if _, err := db.Exec(
			"INSERT INTO contributions (goal_id, amount, date) VALUES (1, 400, ?)", d,
		); err != nil {
			t.Fatalf("inserting contribution: %v", err)
		}
	}

	goals, total, err := loadGoalProgress(db, date("2026-07-29"))
	if err != nil {
		t.Fatalf("loadGoalProgress: %v", err)
	}
	if len(goals) != 2 {
		t.Fatalf("expected 2 goals, got %d", len(goals))
	}
	if !floatEquals(total, 1200) {
		t.Errorf("total saved: got %v, want 1200", total)
	}

	// Goals come back ordered by name, so Camera is first.
	camera, fund := goals[0], goals[1]
	if camera.Name != "Camera" || fund.Name != "Emergency Fund" {
		t.Fatalf("unexpected order: %q then %q", camera.Name, fund.Name)
	}
	if !floatEquals(camera.Saved, 0) || camera.Pace != "none" {
		t.Errorf("unfunded goal with no deadline: got saved %v pace %q, want 0 and \"none\"", camera.Saved, camera.Pace)
	}
	if !floatEquals(fund.Saved, 1200) {
		t.Errorf("Emergency Fund saved: got %v, want 1200", fund.Saved)
	}
	// 1200 over three months of funding (May, June, July).
	if !floatEquals(fund.ObservedPerMonth, 400) {
		t.Errorf("Emergency Fund funding rate: got %v, want 400", fund.ObservedPerMonth)
	}
	// 3800 remaining over 5 months to December is 760 a month, so 400 is behind.
	if !floatEquals(fund.RequiredPerMonth, 760) {
		t.Errorf("Emergency Fund required rate: got %v, want 760", fund.RequiredPerMonth)
	}
	if fund.Pace != "behind" {
		t.Errorf("Emergency Fund pace: got %q, want \"behind\"", fund.Pace)
	}
}
