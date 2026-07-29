package main

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"
)

type incomeInput struct {
	Amount float64 `json:"amount"`
	Source string  `json:"source"`
	Date   string  `json:"date"`
	Note   string  `json:"note"`
}

func (in incomeInput) validate() string {
	if in.Amount <= 0 {
		return "amount must be greater than 0"
	}
	if in.Source == "" {
		return "source is required"
	}
	// Same rule as expenses: a real date, not just the right punctuation, or
	// month grouping in the savings summary silently drops the row.
	if _, err := time.Parse("2006-01-02", in.Date); err != nil {
		return "date must be a real date in YYYY-MM-DD format"
	}
	return ""
}

func incomeRoutes(mux *http.ServeMux, db *sql.DB) {
	mux.HandleFunc("GET /api/income", func(w http.ResponseWriter, r *http.Request) {
		month := r.URL.Query().Get("month")

		var rows *sql.Rows
		var err error
		if month != "" {
			rows, err = db.Query(
				"SELECT id, amount, source, date, note FROM income WHERE date LIKE ? ORDER BY date DESC, id DESC",
				month+"%",
			)
		} else {
			rows, err = db.Query("SELECT id, amount, source, date, note FROM income ORDER BY date DESC, id DESC")
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		defer rows.Close()

		entries := []Income{}
		for rows.Next() {
			var e Income
			var note sql.NullString
			if err := rows.Scan(&e.ID, &e.Amount, &e.Source, &e.Date, &note); err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			e.Note = note.String
			entries = append(entries, e)
		}
		writeJSON(w, http.StatusOK, entries)
	})

	mux.HandleFunc("POST /api/income", func(w http.ResponseWriter, r *http.Request) {
		var in incomeInput
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		in.Source = strings.TrimSpace(in.Source)
		in.Note = strings.TrimSpace(in.Note)
		if msg := in.validate(); msg != "" {
			writeError(w, http.StatusBadRequest, msg)
			return
		}

		res, err := db.Exec(
			"INSERT INTO income (amount, source, date, note) VALUES (?, ?, ?, ?)",
			in.Amount, in.Source, in.Date, in.Note,
		)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		id, _ := res.LastInsertId()
		writeJSON(w, http.StatusCreated, Income{ID: id, Amount: in.Amount, Source: in.Source, Date: in.Date, Note: in.Note})
	})

	mux.HandleFunc("PUT /api/income/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid income id")
			return
		}

		var in incomeInput
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		in.Source = strings.TrimSpace(in.Source)
		in.Note = strings.TrimSpace(in.Note)
		if msg := in.validate(); msg != "" {
			writeError(w, http.StatusBadRequest, msg)
			return
		}

		res, err := db.Exec(
			"UPDATE income SET amount = ?, source = ?, date = ?, note = ? WHERE id = ?",
			in.Amount, in.Source, in.Date, in.Note, id,
		)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if n, _ := res.RowsAffected(); n == 0 {
			writeError(w, http.StatusNotFound, "income entry not found")
			return
		}
		writeJSON(w, http.StatusOK, Income{ID: id, Amount: in.Amount, Source: in.Source, Date: in.Date, Note: in.Note})
	})

	mux.HandleFunc("DELETE /api/income/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid income id")
			return
		}
		res, err := db.Exec("DELETE FROM income WHERE id = ?", id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if n, _ := res.RowsAffected(); n == 0 {
			writeError(w, http.StatusNotFound, "income entry not found")
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})
}
