package main

import (
	"database/sql"
	"fmt"
	"strings"

	_ "modernc.org/sqlite"
)

var defaultCategories = []string{
	"Food", "Transport", "Shopping", "Bills", "Entertainment", "Health", "Other",
}

// InitDB opens (creating if necessary) the SQLite database at path,
// ensures the schema exists, and seeds default data on first run.
func InitDB(path string) (*sql.DB, error) {
	// SQLite ignores REFERENCES clauses unless foreign_keys is on, and it is
	// off by default. Set via DSN so every pooled connection gets it.
	db, err := sql.Open("sqlite", path+"?_pragma=foreign_keys(1)")
	if err != nil {
		return nil, fmt.Errorf("opening db: %w", err)
	}

	schema := []string{
		`CREATE TABLE IF NOT EXISTS categories (
			id   INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL UNIQUE
		)`,
		`CREATE TABLE IF NOT EXISTS expenses (
			id          INTEGER PRIMARY KEY AUTOINCREMENT,
			amount      REAL NOT NULL,
			category_id INTEGER NOT NULL REFERENCES categories(id),
			date        TEXT NOT NULL,
			note        TEXT,
			created_at  TEXT NOT NULL DEFAULT (datetime('now'))
		)`,
		`CREATE TABLE IF NOT EXISTS settings (
			id             INTEGER PRIMARY KEY CHECK (id = 1),
			monthly_budget REAL NOT NULL DEFAULT 0
		)`,
		// Income is what savings are measured against: without it "saved" is
		// only "did not spend", which is a different (and much weaker) claim.
		`CREATE TABLE IF NOT EXISTS income (
			id         INTEGER PRIMARY KEY AUTOINCREMENT,
			amount     REAL NOT NULL,
			source     TEXT NOT NULL,
			date       TEXT NOT NULL,
			note       TEXT,
			created_at TEXT NOT NULL DEFAULT (datetime('now'))
		)`,
		`CREATE TABLE IF NOT EXISTS goals (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			name          TEXT NOT NULL UNIQUE,
			target_amount REAL NOT NULL,
			target_date   TEXT,
			created_at    TEXT NOT NULL DEFAULT (datetime('now'))
		)`,
		// Deleting a goal should take its contributions with it — they have no
		// meaning on their own, and orphans would skew the savings totals.
		`CREATE TABLE IF NOT EXISTS contributions (
			id         INTEGER PRIMARY KEY AUTOINCREMENT,
			goal_id    INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
			amount     REAL NOT NULL,
			date       TEXT NOT NULL,
			note       TEXT,
			created_at TEXT NOT NULL DEFAULT (datetime('now'))
		)`,
	}
	for _, stmt := range schema {
		if _, err := db.Exec(stmt); err != nil {
			db.Close()
			return nil, fmt.Errorf("creating schema: %w", err)
		}
	}

	// Databases created before savings existed already have a settings table, so
	// CREATE TABLE IF NOT EXISTS above silently skips the new column.
	if err := addColumn(db, "settings", "savings_target REAL NOT NULL DEFAULT 0"); err != nil {
		db.Close()
		return nil, fmt.Errorf("upgrading settings: %w", err)
	}

	for _, name := range defaultCategories {
		if _, err := db.Exec(`INSERT OR IGNORE INTO categories (name) VALUES (?)`, name); err != nil {
			db.Close()
			return nil, fmt.Errorf("seeding category %q: %w", name, err)
		}
	}

	if _, err := db.Exec(`INSERT OR IGNORE INTO settings (id, monthly_budget) VALUES (1, 0)`); err != nil {
		db.Close()
		return nil, fmt.Errorf("seeding settings: %w", err)
	}

	return db, nil
}

// addColumn adds a column to an existing table. SQLite has no
// "ADD COLUMN IF NOT EXISTS", and on an already-upgraded database a duplicate
// column is the expected no-op rather than a failure.
func addColumn(db *sql.DB, table, definition string) error {
	_, err := db.Exec("ALTER TABLE " + table + " ADD COLUMN " + definition)
	if err != nil && strings.Contains(err.Error(), "duplicate column name") {
		return nil
	}
	return err
}
