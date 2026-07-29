package main

import "strconv"

type Category struct {
	ID   int64  `json:"id"`
	Name string `json:"name"`
}

type Expense struct {
	ID         int64   `json:"id"`
	Amount     float64 `json:"amount"`
	CategoryID int64   `json:"category_id"`
	Date       string  `json:"date"`
	Note       string  `json:"note"`
}

type Income struct {
	ID     int64   `json:"id"`
	Amount float64 `json:"amount"`
	Source string  `json:"source"`
	Date   string  `json:"date"`
	Note   string  `json:"note"`
}

type Goal struct {
	ID           int64   `json:"id"`
	Name         string  `json:"name"`
	TargetAmount float64 `json:"target_amount"`
	// Empty when the goal has no deadline — saving without one is legitimate,
	// it just means there is no pace to be behind on.
	TargetDate string `json:"target_date"`
}

type Contribution struct {
	ID     int64   `json:"id"`
	GoalID int64   `json:"goal_id"`
	Amount float64 `json:"amount"`
	Date   string  `json:"date"`
	Note   string  `json:"note"`
}

type Settings struct {
	MonthlyBudget float64 `json:"monthly_budget"`
	SavingsTarget float64 `json:"savings_target"`
}

func fmtInt(n int64) string {
	return strconv.FormatInt(n, 10)
}
