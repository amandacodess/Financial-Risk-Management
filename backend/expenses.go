package main

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"
)

type expenseInput struct {
	Amount     float64 `json:"amount"`
	CategoryID int64   `json:"category_id"`
	Date       string  `json:"date"`
	Note       string  `json:"note"`
}

func (in expenseInput) validate() string {
	if in.Amount <= 0 {
		return "amount must be greater than 0"
	}
	if in.CategoryID <= 0 {
		return "category_id is required"
	}
	// Parse, don't just shape-check: "9999-99-99" has the right punctuation but
	// is not a date, and it corrupts month filtering and forecast grouping.
	if _, err := time.Parse("2006-01-02", in.Date); err != nil {
		return "date must be a real date in YYYY-MM-DD format"
	}
	return ""
}

func expensesRoutes(mux *http.ServeMux, db *sql.DB) {
	mux.HandleFunc("GET /api/expenses", func(w http.ResponseWriter, r *http.Request) {
		month := r.URL.Query().Get("month")

		var rows *sql.Rows
		var err error
		if month != "" {
			rows, err = db.Query(
				"SELECT id, amount, category_id, date, note FROM expenses WHERE date LIKE ? ORDER BY date DESC, id DESC",
				month+"%",
			)
		} else {
			rows, err = db.Query("SELECT id, amount, category_id, date, note FROM expenses ORDER BY date DESC, id DESC")
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		defer rows.Close()

		expenses := []Expense{}
		for rows.Next() {
			var e Expense
			var note sql.NullString
			if err := rows.Scan(&e.ID, &e.Amount, &e.CategoryID, &e.Date, &note); err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			e.Note = note.String
			expenses = append(expenses, e)
		}
		writeJSON(w, http.StatusOK, expenses)
	})

	mux.HandleFunc("POST /api/expenses", func(w http.ResponseWriter, r *http.Request) {
		var in expenseInput
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		in.Note = strings.TrimSpace(in.Note)
		if msg := in.validate(); msg != "" {
			writeError(w, http.StatusBadRequest, msg)
			return
		}

		res, err := db.Exec(
			"INSERT INTO expenses (amount, category_id, date, note) VALUES (?, ?, ?, ?)",
			in.Amount, in.CategoryID, in.Date, in.Note,
		)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid category_id or data")
			return
		}
		id, _ := res.LastInsertId()
		writeJSON(w, http.StatusCreated, Expense{ID: id, Amount: in.Amount, CategoryID: in.CategoryID, Date: in.Date, Note: in.Note})
	})

	mux.HandleFunc("PUT /api/expenses/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid expense id")
			return
		}

		var in expenseInput
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		in.Note = strings.TrimSpace(in.Note)
		if msg := in.validate(); msg != "" {
			writeError(w, http.StatusBadRequest, msg)
			return
		}

		res, err := db.Exec(
			"UPDATE expenses SET amount = ?, category_id = ?, date = ?, note = ? WHERE id = ?",
			in.Amount, in.CategoryID, in.Date, in.Note, id,
		)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid category_id or data")
			return
		}
		if n, _ := res.RowsAffected(); n == 0 {
			writeError(w, http.StatusNotFound, "expense not found")
			return
		}
		writeJSON(w, http.StatusOK, Expense{ID: id, Amount: in.Amount, CategoryID: in.CategoryID, Date: in.Date, Note: in.Note})
	})

	mux.HandleFunc("DELETE /api/expenses/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid expense id")
			return
		}
		res, err := db.Exec("DELETE FROM expenses WHERE id = ?", id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if n, _ := res.RowsAffected(); n == 0 {
			writeError(w, http.StatusNotFound, "expense not found")
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})
}
