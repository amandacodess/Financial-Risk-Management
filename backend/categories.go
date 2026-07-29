package main

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
)

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func categoriesRoutes(mux *http.ServeMux, db *sql.DB) {
	mux.HandleFunc("GET /api/categories", func(w http.ResponseWriter, r *http.Request) {
		rows, err := db.Query("SELECT id, name FROM categories ORDER BY name")
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		defer rows.Close()

		cats := []Category{}
		for rows.Next() {
			var c Category
			if err := rows.Scan(&c.ID, &c.Name); err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			cats = append(cats, c)
		}
		writeJSON(w, http.StatusOK, cats)
	})

	mux.HandleFunc("POST /api/categories", func(w http.ResponseWriter, r *http.Request) {
		var in struct {
			Name string `json:"name"`
		}
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body")
			return
		}
		name := strings.TrimSpace(in.Name)
		if name == "" {
			writeError(w, http.StatusBadRequest, "name is required")
			return
		}

		res, err := db.Exec("INSERT INTO categories (name) VALUES (?)", name)
		if err != nil {
			writeError(w, http.StatusBadRequest, "category name already exists or is invalid")
			return
		}
		id, _ := res.LastInsertId()
		writeJSON(w, http.StatusCreated, Category{ID: id, Name: name})
	})

	mux.HandleFunc("DELETE /api/categories/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid category id")
			return
		}

		var exists int
		if err := db.QueryRow("SELECT COUNT(*) FROM categories WHERE id = ?", id).Scan(&exists); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if exists == 0 {
			writeError(w, http.StatusNotFound, "category not found")
			return
		}

		var inUse int
		if err := db.QueryRow("SELECT COUNT(*) FROM expenses WHERE category_id = ?", id).Scan(&inUse); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if inUse > 0 {
			writeError(w, http.StatusConflict, "category is used by existing expenses")
			return
		}

		if _, err := db.Exec("DELETE FROM categories WHERE id = ?", id); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})
}
