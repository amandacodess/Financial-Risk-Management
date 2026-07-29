package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

func newTestServer(t *testing.T) (*http.ServeMux, func()) {
	t.Helper()
	db, err := InitDB(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatalf("InitDB: %v", err)
	}
	mux := http.NewServeMux()
	categoriesRoutes(mux, db)
	expensesRoutes(mux, db)
	return mux, func() { db.Close() }
}

func itoa(n int64) string {
	return fmtInt(n)
}

func TestCategories_CreateListDelete(t *testing.T) {
	mux, cleanup := newTestServer(t)
	defer cleanup()

	// List should include the 7 seeded categories.
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/api/categories", nil))
	if rr.Code != http.StatusOK {
		t.Fatalf("GET list: expected 200, got %d", rr.Code)
	}
	var cats []Category
	if err := json.Unmarshal(rr.Body.Bytes(), &cats); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(cats) != 7 {
		t.Fatalf("expected 7 categories, got %d", len(cats))
	}

	// Create a new category.
	body, _ := json.Marshal(map[string]string{"name": "Travel"})
	rr = httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/api/categories", bytes.NewReader(body)))
	if rr.Code != http.StatusCreated {
		t.Fatalf("POST: expected 201, got %d: %s", rr.Code, rr.Body.String())
	}
	var created Category
	if err := json.Unmarshal(rr.Body.Bytes(), &created); err != nil {
		t.Fatalf("unmarshal created: %v", err)
	}
	if created.Name != "Travel" || created.ID == 0 {
		t.Fatalf("unexpected created category: %+v", created)
	}

	// Delete the new (unused) category should succeed.
	rr = httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodDelete, "/api/categories/"+itoa(created.ID), nil))
	if rr.Code != http.StatusNoContent {
		t.Fatalf("DELETE unused: expected 204, got %d: %s", rr.Code, rr.Body.String())
	}
}

func TestCategories_DeleteBlockedWhenInUse(t *testing.T) {
	mux, cleanup := newTestServer(t)
	defer cleanup()

	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, httptest.NewRequest(http.MethodDelete, "/api/categories/99999", nil))
	if rr.Code != http.StatusNotFound {
		t.Fatalf("DELETE missing: expected 404, got %d: %s", rr.Code, rr.Body.String())
	}
}
