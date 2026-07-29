package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestInitDB_CreatesSchemaAndSeeds(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")

	db, err := InitDB(dbPath)
	if err != nil {
		t.Fatalf("InitDB returned error: %v", err)
	}
	defer db.Close()

	if _, err := os.Stat(dbPath); err != nil {
		t.Fatalf("expected db file to exist: %v", err)
	}

	var categoryCount int
	if err := db.QueryRow("SELECT COUNT(*) FROM categories").Scan(&categoryCount); err != nil {
		t.Fatalf("querying categories: %v", err)
	}
	if categoryCount != 7 {
		t.Errorf("expected 7 seeded categories, got %d", categoryCount)
	}

	var settingsCount int
	if err := db.QueryRow("SELECT COUNT(*) FROM settings").Scan(&settingsCount); err != nil {
		t.Fatalf("querying settings: %v", err)
	}
	if settingsCount != 1 {
		t.Errorf("expected 1 settings row, got %d", settingsCount)
	}

	var budget float64
	if err := db.QueryRow("SELECT monthly_budget FROM settings WHERE id = 1").Scan(&budget); err != nil {
		t.Fatalf("querying budget: %v", err)
	}
	if budget != 0 {
		t.Errorf("expected default budget 0, got %v", budget)
	}

	// Calling InitDB again on the same file must not error or duplicate seed rows.
	db2, err := InitDB(dbPath)
	if err != nil {
		t.Fatalf("second InitDB returned error: %v", err)
	}
	defer db2.Close()

	if err := db2.QueryRow("SELECT COUNT(*) FROM categories").Scan(&categoryCount); err != nil {
		t.Fatalf("querying categories after reopen: %v", err)
	}
	if categoryCount != 7 {
		t.Errorf("expected 7 categories after reopen (no duplicate seeding), got %d", categoryCount)
	}
}
