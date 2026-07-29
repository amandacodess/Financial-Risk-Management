package main

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// GoalProgress is a goal plus the verdict on it: how far along, and whether the
// rate it is actually being funded at reaches the target in time.
type GoalProgress struct {
	Goal
	Saved            float64 `json:"saved"`
	Remaining        float64 `json:"remaining"`
	PercentComplete  float64 `json:"percent_complete"`
	MonthsLeft       int     `json:"months_left"`
	RequiredPerMonth float64 `json:"required_per_month"`
	ObservedPerMonth float64 `json:"observed_per_month"`
	// One of: complete, none (no deadline set), unknown (deadline but no
	// contributions yet), ahead, behind.
	Pace string `json:"pace"`
}

type MonthSavings struct {
	Month  string  `json:"month"`
	Income float64 `json:"income"`
	Spent  float64 `json:"spent"`
	Net    float64 `json:"net"`
	// Share of income kept, as a percentage. Zero when nothing came in — a
	// month with no income has no rate rather than a rate of minus infinity.
	Rate float64 `json:"rate"`
}

type SavingsSummary struct {
	Target        float64        `json:"target"`
	Current       MonthSavings   `json:"current"`
	History       []MonthSavings `json:"history"`
	AverageRate   float64        `json:"average_rate"`
	TotalSaved    float64        `json:"total_saved"`
	MeetingTarget bool           `json:"meeting_target"`
	Goals         []GoalProgress `json:"goals"`
}

// computeMonthSavings turns one month's income and spend into a savings figure.
func computeMonthSavings(month string, income, spent float64) MonthSavings {
	net := income - spent
	rate := 0.0
	if income > 0 {
		rate = net / income * 100
	}
	return MonthSavings{Month: month, Income: income, Spent: spent, Net: net, Rate: rate}
}

// computeGoalProgress judges a goal. monthsLeft is -1 when the goal has no
// deadline, in which case there is no pace to be ahead of or behind.
func computeGoalProgress(g Goal, saved, observedPerMonth float64, monthsLeft int, hasHistory bool) GoalProgress {
	p := GoalProgress{
		Goal:             g,
		Saved:            saved,
		MonthsLeft:       monthsLeft,
		ObservedPerMonth: observedPerMonth,
	}
	if g.TargetAmount > 0 {
		p.PercentComplete = saved / g.TargetAmount * 100
		if p.PercentComplete > 100 {
			p.PercentComplete = 100
		}
	}
	p.Remaining = g.TargetAmount - saved
	if p.Remaining < 0 {
		p.Remaining = 0
	}

	switch {
	case g.TargetAmount > 0 && saved >= g.TargetAmount:
		p.Pace = "complete"
	case monthsLeft < 0:
		p.Pace = "none"
	case monthsLeft == 0:
		// Due this month or already past: the whole remainder is owed now, so
		// there is no rate that makes this anything but behind.
		p.RequiredPerMonth = p.Remaining
		p.Pace = "behind"
	default:
		p.RequiredPerMonth = p.Remaining / float64(monthsLeft)
		if !hasHistory {
			p.Pace = "unknown"
		} else if observedPerMonth >= p.RequiredPerMonth {
			p.Pace = "ahead"
		} else {
			p.Pace = "behind"
		}
	}
	return p
}

// monthsBetween counts whole calendar months from a to b, negative when b is
// the earlier of the two.
func monthsBetween(a, b time.Time) int {
	return (b.Year()-a.Year())*12 + int(b.Month()) - int(a.Month())
}

// monthsUntil counts whole calendar months from now to a YYYY-MM-DD date.
// Returns -1 if the date is absent or unparseable, meaning "no deadline";
// a date in the past clamps to 0, meaning "owed now".
func monthsUntil(now time.Time, date string) int {
	if date == "" {
		return -1
	}
	t, err := time.Parse("2006-01-02", date)
	if err != nil {
		return -1
	}
	if months := monthsBetween(now, t); months > 0 {
		return months
	}
	return 0
}

// monthsFunding is how many months a goal has been receiving contributions,
// counting the month of the first one. Always at least 1, so it can divide.
func monthsFunding(now time.Time, firstContribution string) int {
	t, err := time.Parse("2006-01-02", firstContribution)
	if err != nil {
		return 1
	}
	if elapsed := monthsBetween(t, now) + 1; elapsed > 1 {
		return elapsed
	}
	return 1
}

// lastMonths lists the n months ending with the one containing now, oldest first.
func lastMonths(now time.Time, n int) []string {
	// Step from the first of the month: subtracting a month from the 31st
	// overflows into the wrong month (Mar 31 - 1mo normalises to Mar 3).
	first := time.Date(now.Year(), now.Month(), 1, 0, 0, 0, 0, now.Location())
	months := make([]string, 0, n)
	for i := n - 1; i >= 0; i-- {
		months = append(months, first.AddDate(0, -i, 0).Format("2006-01"))
	}
	return months
}

// averageRate averages the savings rate over months that had income; months
// with none would otherwise drag the average toward zero for no reason.
func averageRate(history []MonthSavings) float64 {
	sum, n := 0.0, 0
	for _, m := range history {
		if m.Income > 0 {
			sum += m.Rate
			n++
		}
	}
	if n == 0 {
		return 0
	}
	return sum / float64(n)
}

type goalInput struct {
	Name         string  `json:"name"`
	TargetAmount float64 `json:"target_amount"`
	TargetDate   string  `json:"target_date"`
}

func (in goalInput) validate() string {
	if in.Name == "" {
		return "name is required"
	}
	if in.TargetAmount <= 0 {
		return "target_amount must be greater than 0"
	}
	if in.TargetDate != "" {
		if _, err := time.Parse("2006-01-02", in.TargetDate); err != nil {
			return "target_date must be a real date in YYYY-MM-DD format"
		}
	}
	return ""
}

// monthTotals sums a dated amount column by month across a whole table.
func monthTotals(db *sql.DB, table string) (map[string]float64, error) {
	rows, err := db.Query(
		"SELECT strftime('%Y-%m', date) AS m, SUM(amount) FROM " + table + " GROUP BY m",
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	totals := map[string]float64{}
	for rows.Next() {
		var month string
		var total float64
		if err := rows.Scan(&month, &total); err != nil {
			return nil, err
		}
		totals[month] = total
	}
	return totals, rows.Err()
}

func loadGoalProgress(db *sql.DB, now time.Time) ([]GoalProgress, float64, error) {
	rows, err := db.Query(`
		SELECT g.id, g.name, g.target_amount, COALESCE(g.target_date, ''),
		       COALESCE(SUM(c.amount), 0), COALESCE(MIN(c.date), '')
		FROM goals g
		LEFT JOIN contributions c ON c.goal_id = g.id
		GROUP BY g.id
		ORDER BY g.name
	`)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	goals := []GoalProgress{}
	total := 0.0
	for rows.Next() {
		var g Goal
		var saved float64
		var firstContribution string
		if err := rows.Scan(&g.ID, &g.Name, &g.TargetAmount, &g.TargetDate, &saved, &firstContribution); err != nil {
			return nil, 0, err
		}
		total += saved

		// Funding rate so far: what has gone in, over the months it has been
		// going in for. The month of the first contribution counts as one.
		hasHistory := firstContribution != ""
		observed := 0.0
		if hasHistory {
			observed = saved / float64(monthsFunding(now, firstContribution))
		}
		goals = append(goals, computeGoalProgress(g, saved, observed, monthsUntil(now, g.TargetDate), hasHistory))
	}
	return goals, total, rows.Err()
}

func savingsRoutes(mux *http.ServeMux, db *sql.DB) {
	mux.HandleFunc("GET /api/savings", func(w http.ResponseWriter, r *http.Request) {
		now := time.Now()

		incomeByMonth, err := monthTotals(db, "income")
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		spendByMonth, err := monthTotals(db, "expenses")
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		history := []MonthSavings{}
		for _, m := range lastMonths(now, 6) {
			history = append(history, computeMonthSavings(m, incomeByMonth[m], spendByMonth[m]))
		}
		current := history[len(history)-1]

		var target float64
		if err := db.QueryRow("SELECT savings_target FROM settings WHERE id = 1").Scan(&target); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		goals, totalSaved, err := loadGoalProgress(db, now)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		writeJSON(w, http.StatusOK, SavingsSummary{
			Target:        target,
			Current:       current,
			History:       history,
			AverageRate:   averageRate(history),
			TotalSaved:    totalSaved,
			MeetingTarget: target > 0 && current.Net >= target,
			Goals:         goals,
		})
	})

	mux.HandleFunc("POST /api/goals", func(w http.ResponseWriter, r *http.Request) {
		var in goalInput
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		in.Name = strings.TrimSpace(in.Name)
		in.TargetDate = strings.TrimSpace(in.TargetDate)
		if msg := in.validate(); msg != "" {
			writeError(w, http.StatusBadRequest, msg)
			return
		}

		res, err := db.Exec(
			"INSERT INTO goals (name, target_amount, target_date) VALUES (?, ?, ?)",
			in.Name, in.TargetAmount, in.TargetDate,
		)
		if err != nil {
			writeError(w, http.StatusBadRequest, "a goal with that name already exists")
			return
		}
		id, _ := res.LastInsertId()
		writeJSON(w, http.StatusCreated, Goal{ID: id, Name: in.Name, TargetAmount: in.TargetAmount, TargetDate: in.TargetDate})
	})

	mux.HandleFunc("PUT /api/goals/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid goal id")
			return
		}

		var in goalInput
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		in.Name = strings.TrimSpace(in.Name)
		in.TargetDate = strings.TrimSpace(in.TargetDate)
		if msg := in.validate(); msg != "" {
			writeError(w, http.StatusBadRequest, msg)
			return
		}

		res, err := db.Exec(
			"UPDATE goals SET name = ?, target_amount = ?, target_date = ? WHERE id = ?",
			in.Name, in.TargetAmount, in.TargetDate, id,
		)
		if err != nil {
			writeError(w, http.StatusBadRequest, "a goal with that name already exists")
			return
		}
		if n, _ := res.RowsAffected(); n == 0 {
			writeError(w, http.StatusNotFound, "goal not found")
			return
		}
		writeJSON(w, http.StatusOK, Goal{ID: id, Name: in.Name, TargetAmount: in.TargetAmount, TargetDate: in.TargetDate})
	})

	// Contributions go with the goal: on their own they mean nothing, and the
	// schema cascades the delete for the same reason.
	mux.HandleFunc("DELETE /api/goals/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid goal id")
			return
		}
		res, err := db.Exec("DELETE FROM goals WHERE id = ?", id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if n, _ := res.RowsAffected(); n == 0 {
			writeError(w, http.StatusNotFound, "goal not found")
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

	mux.HandleFunc("GET /api/goals/{id}/contributions", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid goal id")
			return
		}
		rows, err := db.Query(
			"SELECT id, goal_id, amount, date, note FROM contributions WHERE goal_id = ? ORDER BY date DESC, id DESC",
			id,
		)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		defer rows.Close()

		items := []Contribution{}
		for rows.Next() {
			var c Contribution
			var note sql.NullString
			if err := rows.Scan(&c.ID, &c.GoalID, &c.Amount, &c.Date, &note); err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			c.Note = note.String
			items = append(items, c)
		}
		writeJSON(w, http.StatusOK, items)
	})

	mux.HandleFunc("POST /api/goals/{id}/contributions", func(w http.ResponseWriter, r *http.Request) {
		goalID, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid goal id")
			return
		}

		var in struct {
			Amount float64 `json:"amount"`
			Date   string  `json:"date"`
			Note   string  `json:"note"`
		}
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		if in.Amount <= 0 {
			writeError(w, http.StatusBadRequest, "amount must be greater than 0")
			return
		}
		if _, err := time.Parse("2006-01-02", in.Date); err != nil {
			writeError(w, http.StatusBadRequest, "date must be a real date in YYYY-MM-DD format")
			return
		}
		in.Note = strings.TrimSpace(in.Note)

		res, err := db.Exec(
			"INSERT INTO contributions (goal_id, amount, date, note) VALUES (?, ?, ?, ?)",
			goalID, in.Amount, in.Date, in.Note,
		)
		if err != nil {
			writeError(w, http.StatusBadRequest, "goal not found")
			return
		}
		id, _ := res.LastInsertId()
		writeJSON(w, http.StatusCreated, Contribution{ID: id, GoalID: goalID, Amount: in.Amount, Date: in.Date, Note: in.Note})
	})

	mux.HandleFunc("DELETE /api/contributions/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid contribution id")
			return
		}
		res, err := db.Exec("DELETE FROM contributions WHERE id = ?", id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if n, _ := res.RowsAffected(); n == 0 {
			writeError(w, http.StatusNotFound, "contribution not found")
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})
}
