package main

import (
	"log"
	"net/http"
	"os"
	"strings"
)

func main() {
	loadDotEnv(".env")

	db, err := InitDB("expense-tracker.db")
	if err != nil {
		log.Fatalf("failed to initialize database: %v", err)
	}
	defer db.Close()

	mux := http.NewServeMux()
	categoriesRoutes(mux, db)
	expensesRoutes(mux, db)
	incomeRoutes(mux, db)
	savingsRoutes(mux, db)
	settingsRoutes(mux, db)
	predictionRoutes(mux, db)
	geminiRoutes(mux, db)

	// Say up front whether written analysis will work — better than a silent
	// "unavailable" panel in the interface an hour later.
	if os.Getenv("GEMINI_API_KEY") == "" {
		log.Println("gemini: disabled (no GEMINI_API_KEY; forecasts and everything else still work)")
	} else {
		log.Printf("gemini: enabled (model %s)", geminiModel())
	}

	addr := serverAddr()
	log.Printf("listening on http://%s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}

func serverAddr() string {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	if strings.Contains(port, ":") {
		return port
	}
	return "localhost:" + port
}
