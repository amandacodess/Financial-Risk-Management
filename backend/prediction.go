package main

import (
	"database/sql"
	"net/http"
	"sort"
	"time"
)

type ForecastEntry struct {
	Category        string  `json:"category"`
	PredictedAmount float64 `json:"predicted_amount"`
}

type BudgetAlert struct {
	MonthlyBudget    float64 `json:"monthly_budget"`
	SpentSoFar       float64 `json:"spent_so_far"`
	DaysElapsed      int     `json:"days_elapsed"`
	DaysInMonth      int     `json:"days_in_month"`
	ProjectedTotal   float64 `json:"projected_total"`
	ProjectedOverage float64 `json:"projected_overage"`
	OverBudget       bool    `json:"over_budget"`
}

// computeBudgetAlert projects the current month's total spend based on the
// pace of spending so far and compares it to the monthly budget.
func computeBudgetAlert(monthlyBudget, spentSoFar float64, daysElapsed, daysInMonth int) BudgetAlert {
	var projected float64
	if daysElapsed > 0 {
		projected = spentSoFar * float64(daysInMonth) / float64(daysElapsed)
	}
	// A budget of 0 means "not set yet", not "spend nothing" — otherwise every
	// new user gets a red overspend warning before configuring anything.
	budgetSet := monthlyBudget > 0
	overage := projected - monthlyBudget
	if overage < 0 || !budgetSet {
		overage = 0
	}
	return BudgetAlert{
		MonthlyBudget:    monthlyBudget,
		SpentSoFar:       spentSoFar,
		DaysElapsed:      daysElapsed,
		DaysInMonth:      daysInMonth,
		ProjectedTotal:   projected,
		ProjectedOverage: overage,
		OverBudget:       budgetSet && projected > monthlyBudget,
	}
}

// computeForecast averages each category's totals over up to the last 3
// completed months. Categories with no history are omitted.
func computeForecast(monthlyCategoryTotals map[string][]float64) []ForecastEntry {
	forecast := []ForecastEntry{}
	for category, totals := range monthlyCategoryTotals {
		if len(totals) == 0 {
			continue
		}
		sum := 0.0
		for _, v := range totals {
			sum += v
		}
		forecast = append(forecast, ForecastEntry{
			Category:        category,
			PredictedAmount: sum / float64(len(totals)),
		})
	}
	// Map iteration order is randomised, so without this the dashboard bars
	// reshuffle on every reload. Biggest predicted spend first, name as tiebreak.
	sort.Slice(forecast, func(i, j int) bool {
		if forecast[i].PredictedAmount != forecast[j].PredictedAmount {
			return forecast[i].PredictedAmount > forecast[j].PredictedAmount
		}
		return forecast[i].Category < forecast[j].Category
	})
	return forecast
}

func predictionRoutes(mux *http.ServeMux, db *sql.DB) {
	mux.HandleFunc("GET /api/prediction", func(w http.ResponseWriter, r *http.Request) {
		now := time.Now()
		currentMonth := now.Format("2006-01")
		daysInMonth := time.Date(now.Year(), now.Month()+1, 0, 0, 0, 0, 0, now.Location()).Day()
		daysElapsed := now.Day()

		var spentSoFar float64
		if err := db.QueryRow(
			"SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date LIKE ?", currentMonth+"%",
		).Scan(&spentSoFar); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		var budget float64
		if err := db.QueryRow("SELECT monthly_budget FROM settings WHERE id = 1").Scan(&budget); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		// Last 3 completed months' per-category totals, keyed by category name.
		monthlyTotals := map[string][]float64{}
		rows, err := db.Query(`
			SELECT c.name, strftime('%Y-%m', e.date) AS month, SUM(e.amount)
			FROM expenses e
			JOIN categories c ON c.id = e.category_id
			WHERE e.date < ?
			GROUP BY c.name, month
			ORDER BY month DESC
		`, currentMonth+"-01")
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		defer rows.Close()

		seenMonthsPerCategory := map[string]map[string]bool{}
		for rows.Next() {
			var category, month string
			var total float64
			if err := rows.Scan(&category, &month, &total); err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			if seenMonthsPerCategory[category] == nil {
				seenMonthsPerCategory[category] = map[string]bool{}
			}
			if len(seenMonthsPerCategory[category]) >= 3 {
				continue // only keep the 3 most recent months per category
			}
			seenMonthsPerCategory[category][month] = true
			monthlyTotals[category] = append(monthlyTotals[category], total)
		}

		forecast := computeForecast(monthlyTotals)
		alert := computeBudgetAlert(budget, spentSoFar, daysElapsed, daysInMonth)

		writeJSON(w, http.StatusOK, map[string]any{
			"forecast":     forecast,
			"budget_alert": alert,
		})
	})
}
