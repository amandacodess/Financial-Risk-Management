package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestExpenses_CreateListFilterUpdateDelete(t *testing.T) {
	mux, cleanup := newTestServer(t)
	defer cleanup()

	create := func(amount float64, categoryID int64, date, note string) Expense {
		body, _ := json.Marshal(map[string]interface{}{
			"amount": amount, "category_id": categoryID, "date": date, "note": note,
		})
		rr := httptest.NewRecorder()
		mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/api/expenses", bytes.NewReader(body)))
		if rr.Code != http.StatusCreated {
			t.Fatalf("POST expense: expected 201, got %d: %s", rr.Code, rr.Body.String())
		}
		var e Expense
		json.Unmarshal(rr.Body.Bytes(), &e)
		return e
	}

	e1 := create(50.0, 1, "2026-07-10", "lunch")
	create(20.0, 1, "2026-06-15", "old lunch")

	// List filtered by month should only return July expense.
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/api/expenses?month=2026-07", nil))
	if rr.Code != http.StatusOK {
		t.Fatalf("GET filtered: expected 200, got %d", rr.Code)
	}
	var julyExpenses []Expense
	json.Unmarshal(rr.Body.Bytes(), &julyExpenses)
	if len(julyExpenses) != 1 || julyExpenses[0].Note != "lunch" {
		t.Fatalf("expected 1 July expense, got %+v", julyExpenses)
	}

	// Update the expense.
	body, _ := json.Marshal(map[string]interface{}{
		"amount": 75.0, "category_id": 1, "date": "2026-07-10", "note": "lunch updated",
	})
	rr = httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPut, "/api/expenses/"+itoa(e1.ID), bytes.NewReader(body)))
	if rr.Code != http.StatusOK {
		t.Fatalf("PUT: expected 200, got %d: %s", rr.Code, rr.Body.String())
	}
	var updated Expense
	json.Unmarshal(rr.Body.Bytes(), &updated)
	if updated.Amount != 75.0 || updated.Note != "lunch updated" {
		t.Fatalf("unexpected updated expense: %+v", updated)
	}

	// Delete it.
	rr = httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodDelete, "/api/expenses/"+itoa(e1.ID), nil))
	if rr.Code != http.StatusNoContent {
		t.Fatalf("DELETE: expected 204, got %d", rr.Code)
	}
}

func TestExpenses_CreateValidation(t *testing.T) {
	mux, cleanup := newTestServer(t)
	defer cleanup()

	cases := []struct {
		name string
		body map[string]interface{}
	}{
		{"zero amount", map[string]interface{}{"amount": 0, "category_id": 1, "date": "2026-07-10"}},
		{"negative amount", map[string]interface{}{"amount": -5, "category_id": 1, "date": "2026-07-10"}},
		// Right shape, impossible date: the old length/dash check let this through,
		// which broke month filtering and forecast grouping.
		{"impossible date", map[string]interface{}{"amount": 10, "category_id": 1, "date": "9999-99-99"}},
		{"day out of range", map[string]interface{}{"amount": 10, "category_id": 1, "date": "2026-02-30"}},
		{"not a date at all", map[string]interface{}{"amount": 10, "category_id": 1, "date": "yesterday!"}},
		// SQLite ignores REFERENCES unless the foreign_keys pragma is on, so this
		// used to be accepted and then rendered as "Unknown" forever.
		{"nonexistent category", map[string]interface{}{"amount": 10, "category_id": 9999, "date": "2026-07-10"}},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			body, _ := json.Marshal(c.body)
			rr := httptest.NewRecorder()
			mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/api/expenses", bytes.NewReader(body)))
			if rr.Code != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d: %s", rr.Code, rr.Body.String())
			}
		})
	}
}

// The same validation has to hold on update, not just create.
func TestExpenses_UpdateRejectsBadInput(t *testing.T) {
	mux, cleanup := newTestServer(t)
	defer cleanup()

	body, _ := json.Marshal(map[string]interface{}{
		"amount": 50.0, "category_id": 1, "date": "2026-07-10", "note": "lunch",
	})
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/api/expenses", bytes.NewReader(body)))
	var e Expense
	json.Unmarshal(rr.Body.Bytes(), &e)

	for _, bad := range []map[string]interface{}{
		{"amount": 50.0, "category_id": 9999, "date": "2026-07-10"},
		{"amount": 50.0, "category_id": 1, "date": "2026-13-01"},
	} {
		body, _ := json.Marshal(bad)
		rr := httptest.NewRecorder()
		mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPut, "/api/expenses/"+itoa(e.ID), bytes.NewReader(body)))
		if rr.Code != http.StatusBadRequest {
			t.Fatalf("PUT %v: expected 400, got %d: %s", bad, rr.Code, rr.Body.String())
		}
	}
}
