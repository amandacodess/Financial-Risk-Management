package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

func newSettingsTestServer(t *testing.T) (*http.ServeMux, func()) {
	t.Helper()
	db, err := InitDB(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatalf("InitDB: %v", err)
	}
	mux := http.NewServeMux()
	settingsRoutes(mux, db)
	return mux, func() { db.Close() }
}

func TestSettings_GetAndUpdate(t *testing.T) {
	mux, cleanup := newSettingsTestServer(t)
	defer cleanup()

	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/api/settings", nil))
	if rr.Code != http.StatusOK {
		t.Fatalf("GET: expected 200, got %d", rr.Code)
	}
	var s Settings
	json.Unmarshal(rr.Body.Bytes(), &s)
	if s.MonthlyBudget != 0 {
		t.Fatalf("expected default budget 0, got %v", s.MonthlyBudget)
	}

	body, _ := json.Marshal(map[string]float64{"monthly_budget": 1500})
	rr = httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPut, "/api/settings", bytes.NewReader(body)))
	if rr.Code != http.StatusOK {
		t.Fatalf("PUT: expected 200, got %d: %s", rr.Code, rr.Body.String())
	}
	json.Unmarshal(rr.Body.Bytes(), &s)
	if s.MonthlyBudget != 1500 {
		t.Fatalf("expected updated budget 1500, got %v", s.MonthlyBudget)
	}

	rr = httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/api/settings", nil))
	json.Unmarshal(rr.Body.Bytes(), &s)
	if s.MonthlyBudget != 1500 {
		t.Fatalf("expected persisted budget 1500, got %v", s.MonthlyBudget)
	}
}

// Each setting is saved from its own form, so a request carries only the field
// that changed. The one left out must survive.
func TestSettings_PartialUpdateLeavesOtherFieldAlone(t *testing.T) {
	mux, cleanup := newSettingsTestServer(t)
	defer cleanup()

	put := func(body string) Settings {
		t.Helper()
		rr := httptest.NewRecorder()
		mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPut, "/api/settings", bytes.NewReader([]byte(body))))
		if rr.Code != http.StatusOK {
			t.Fatalf("PUT %s: expected 200, got %d: %s", body, rr.Code, rr.Body.String())
		}
		var s Settings
		json.Unmarshal(rr.Body.Bytes(), &s)
		return s
	}

	put(`{"monthly_budget": 2000}`)
	put(`{"savings_target": 500}`)

	got := put(`{"monthly_budget": 2200}`)
	if got.MonthlyBudget != 2200 {
		t.Errorf("monthly_budget: got %v, want 2200", got.MonthlyBudget)
	}
	if got.SavingsTarget != 500 {
		t.Errorf("savings_target was wiped by a budget-only update: got %v, want 500", got.SavingsTarget)
	}

	// Zero is a real value — clearing a target must still work.
	if cleared := put(`{"savings_target": 0}`); cleared.SavingsTarget != 0 {
		t.Errorf("savings_target should be clearable to 0, got %v", cleared.SavingsTarget)
	}
}

func TestSettings_RejectsNegativeValues(t *testing.T) {
	mux, cleanup := newSettingsTestServer(t)
	defer cleanup()

	for _, body := range []string{`{"monthly_budget": -1}`, `{"savings_target": -1}`} {
		rr := httptest.NewRecorder()
		mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPut, "/api/settings", bytes.NewReader([]byte(body))))
		if rr.Code != http.StatusBadRequest {
			t.Errorf("PUT %s: expected 400, got %d", body, rr.Code)
		}
	}
}
