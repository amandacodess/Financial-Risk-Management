package main

import (
	"database/sql"
	"encoding/json"
	"net/http"
)

func settingsRoutes(mux *http.ServeMux, db *sql.DB) {
	mux.HandleFunc("GET /api/settings", func(w http.ResponseWriter, r *http.Request) {
		var s Settings
		if err := db.QueryRow(
			"SELECT monthly_budget, savings_target FROM settings WHERE id = 1",
		).Scan(&s.MonthlyBudget, &s.SavingsTarget); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, s)
	})

	mux.HandleFunc("PUT /api/settings", func(w http.ResponseWriter, r *http.Request) {
		// Pointers so an omitted field means "leave it alone" rather than
		// "set it to zero" — otherwise saving a budget wipes the savings target.
		var in struct {
			MonthlyBudget *float64 `json:"monthly_budget"`
			SavingsTarget *float64 `json:"savings_target"`
		}
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}

		updates := []struct {
			column string
			value  *float64
		}{
			{"monthly_budget", in.MonthlyBudget},
			{"savings_target", in.SavingsTarget},
		}
		for _, u := range updates {
			if u.value == nil {
				continue
			}
			if *u.value < 0 {
				writeError(w, http.StatusBadRequest, u.column+" cannot be negative")
				return
			}
			if _, err := db.Exec("UPDATE settings SET "+u.column+" = ? WHERE id = 1", *u.value); err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
		}

		var s Settings
		if err := db.QueryRow(
			"SELECT monthly_budget, savings_target FROM settings WHERE id = 1",
		).Scan(&s.MonthlyBudget, &s.SavingsTarget); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, s)
	})
}
