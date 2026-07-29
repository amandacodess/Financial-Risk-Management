package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// Gemini writes the analysis that sits alongside the arithmetic forecast. The
// forecast itself stays local and deterministic, so the app is fully usable
// with no key, no network, and no account.

const defaultGeminiModel = "gemini-3.6-flash"

const insightPrompt = `You are a careful bookkeeper reviewing a client's ledger. Below is their spending, income, and savings record.

Write exactly two short paragraphs of plain prose, separated by one blank line.

Paragraph one: the single most important pattern in this data. Name the specific categories and figures that show it. Prefer a trend across months over a restatement of the latest total — they can already see the totals.
Paragraph two: one concrete, specific action, with the amount it would save or free up per month and what it would change.

Rules: no markdown, no headings, no bullets, no preamble, no sign-off. Address them as "you". Be direct and specific about figures. Every amount below is in Indian rupees: write figures with the ₹ symbol and group them the Indian way (₹1,23,456), never with a dollar sign. If the record is too thin to support a real observation, say so plainly in one sentence instead of inventing a pattern.

LEDGER
%s`

// loadDotEnv reads KEY=value lines from path into the environment. Real
// environment variables win, so an exported key overrides the file.
func loadDotEnv(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return // no .env is the normal case
	}
	for line := range strings.SplitSeq(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		value = strings.Trim(strings.TrimSpace(value), `"'`)
		if _, exists := os.LookupEnv(key); !exists {
			os.Setenv(key, value)
		}
	}
}

func geminiModel() string {
	if m := os.Getenv("GEMINI_MODEL"); m != "" {
		return m
	}
	return defaultGeminiModel
}

type geminiPart struct {
	Text string `json:"text"`
}

type geminiContent struct {
	Parts []geminiPart `json:"parts"`
}

type geminiRequest struct {
	Contents         []geminiContent `json:"contents"`
	GenerationConfig struct {
		Temperature     float64 `json:"temperature"`
		MaxOutputTokens int     `json:"maxOutputTokens"`
		ThinkingConfig  struct {
			ThinkingLevel string `json:"thinkingLevel"`
		} `json:"thinkingConfig"`
	} `json:"generationConfig"`
}

type geminiResponse struct {
	Candidates []struct {
		Content      geminiContent `json:"content"`
		FinishReason string        `json:"finishReason"`
	} `json:"candidates"`
	PromptFeedback struct {
		BlockReason string `json:"blockReason"`
	} `json:"promptFeedback"`
	Error struct {
		Message string `json:"message"`
	} `json:"error"`
}

// extractText pulls the reply out of a decoded response, turning Gemini's
// several ways of saying "no answer" into one error.
func extractText(resp geminiResponse) (string, error) {
	if resp.Error.Message != "" {
		return "", fmt.Errorf("gemini: %s", resp.Error.Message)
	}
	if resp.PromptFeedback.BlockReason != "" {
		return "", fmt.Errorf("gemini blocked the request (%s)", resp.PromptFeedback.BlockReason)
	}
	if len(resp.Candidates) == 0 {
		return "", fmt.Errorf("gemini returned no analysis")
	}
	var b strings.Builder
	for _, part := range resp.Candidates[0].Content.Parts {
		b.WriteString(part.Text)
	}
	text := strings.TrimSpace(b.String())
	if text == "" {
		// Usually the budget was spent on reasoning tokens before any prose.
		return "", fmt.Errorf("gemini returned an empty analysis (finish reason: %s)", resp.Candidates[0].FinishReason)
	}
	return text, nil
}

func callGemini(ctx context.Context, apiKey, model, prompt string) (string, error) {
	var body geminiRequest
	body.Contents = []geminiContent{{Parts: []geminiPart{{Text: prompt}}}}
	body.GenerationConfig.Temperature = 0.4
	// Thinking tokens count against this too, so it is well above what two
	// paragraphs of prose need on their own.
	body.GenerationConfig.MaxOutputTokens = 2000
	// Reasoning tokens count against MaxOutputTokens, and a review this small
	// does not need many — left high, the budget can be gone before any prose.
	body.GenerationConfig.ThinkingConfig.ThinkingLevel = "low"

	payload, err := json.Marshal(body)
	if err != nil {
		return "", err
	}

	url := "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(payload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	// Header rather than a query parameter: keys in URLs end up in logs.
	req.Header.Set("x-goog-api-key", apiKey)

	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("could not reach Gemini: %w", err)
	}
	defer res.Body.Close()

	var decoded geminiResponse
	if err := json.NewDecoder(res.Body).Decode(&decoded); err != nil {
		return "", fmt.Errorf("gemini returned an unreadable response (HTTP %d)", res.StatusCode)
	}
	if text, err := extractText(decoded); err == nil {
		return text, nil
	} else if res.StatusCode != http.StatusOK {
		return "", fmt.Errorf("gemini rejected the request (HTTP %d): %s", res.StatusCode, decoded.Error.Message)
	} else {
		return "", err
	}
}

// spendingDigest renders the figures Gemini is asked to analyse. Deliberately
// aggregates: category, goal and source names go, but the free-text notes on
// individual entries never leave this machine.
func spendingDigest(db *sql.DB, now time.Time) (string, bool, error) {
	var b strings.Builder
	fmt.Fprintf(&b, "Today: %s\n", now.Format("2006-01-02"))

	var budget, savingsTarget float64
	if err := db.QueryRow(
		"SELECT monthly_budget, savings_target FROM settings WHERE id = 1",
	).Scan(&budget, &savingsTarget); err != nil {
		return "", false, err
	}
	fmt.Fprintf(&b, "Monthly spending budget: %.2f (0 means not set)\n", budget)
	fmt.Fprintf(&b, "Monthly savings target: %.2f (0 means not set)\n\n", savingsTarget)

	rows, err := db.Query(`
		SELECT strftime('%Y-%m', e.date) AS month, c.name, SUM(e.amount)
		FROM expenses e
		JOIN categories c ON c.id = e.category_id
		GROUP BY month, c.name
		ORDER BY month, c.name
	`)
	if err != nil {
		return "", false, err
	}
	defer rows.Close()

	byMonth := map[string][]string{}
	months := []string{}
	hasSpending := false
	for rows.Next() {
		var month, category string
		var total float64
		if err := rows.Scan(&month, &category, &total); err != nil {
			return "", false, err
		}
		if _, seen := byMonth[month]; !seen {
			months = append(months, month)
		}
		byMonth[month] = append(byMonth[month], fmt.Sprintf("%s %.2f", category, total))
		hasSpending = true
	}
	if err := rows.Err(); err != nil {
		return "", false, err
	}

	b.WriteString("Spending by month and category:\n")
	if !hasSpending {
		b.WriteString("  (nothing recorded)\n")
	}
	// Recent months are what an observation should be about; older ones are
	// only there for the trend, so cap the list rather than send everything.
	if len(months) > 12 {
		months = months[len(months)-12:]
	}
	for _, m := range months {
		fmt.Fprintf(&b, "  %s  %s\n", m, strings.Join(byMonth[m], " | "))
	}

	incomeByMonth, err := monthTotals(db, "income")
	if err != nil {
		return "", false, err
	}
	b.WriteString("\nIncome by month:\n")
	if len(incomeByMonth) == 0 {
		b.WriteString("  (nothing recorded)\n")
	}
	for _, m := range lastMonths(now, 12) {
		if total, ok := incomeByMonth[m]; ok {
			fmt.Fprintf(&b, "  %s  %.2f\n", m, total)
		}
	}

	goals, totalSaved, err := loadGoalProgress(db, now)
	if err != nil {
		return "", false, err
	}
	b.WriteString("\nSavings goals:\n")
	if len(goals) == 0 {
		b.WriteString("  (none set)\n")
	}
	for _, g := range goals {
		deadline := "no deadline"
		if g.TargetDate != "" {
			deadline = "by " + g.TargetDate
		}
		fmt.Fprintf(&b, "  %s: saved %.2f of %.2f, %s, needs %.2f/mo, funded at %.2f/mo, status %s\n",
			g.Name, g.Saved, g.TargetAmount, deadline, g.RequiredPerMonth, g.ObservedPerMonth, g.Pace)
	}
	fmt.Fprintf(&b, "Total put aside across all goals: %.2f\n", totalSaved)

	return b.String(), hasSpending, nil
}

// ponytail: one cached answer for the whole app, which is right for a
// single-user local ledger. Key it per-user if this ever serves more than one.
type insightCache struct {
	mu        sync.Mutex
	digest    string
	text      string
	generated time.Time
}

func (c *insightCache) get(digest string) (string, time.Time, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.digest == digest && c.text != "" {
		return c.text, c.generated, true
	}
	return "", time.Time{}, false
}

func (c *insightCache) put(digest, text string, at time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.digest, c.text, c.generated = digest, text, at
}

func geminiRoutes(mux *http.ServeMux, db *sql.DB) {
	cache := &insightCache{}

	mux.HandleFunc("GET /api/insight", func(w http.ResponseWriter, r *http.Request) {
		apiKey := os.Getenv("GEMINI_API_KEY")
		if apiKey == "" {
			writeJSON(w, http.StatusOK, map[string]any{
				"available": false,
				"reason":    "Add GEMINI_API_KEY to backend/.env and restart the server to turn on written analysis.",
			})
			return
		}

		digest, hasSpending, err := spendingDigest(db, time.Now())
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if !hasSpending {
			writeJSON(w, http.StatusOK, map[string]any{
				"available": false,
				"reason":    "Record a few expenses and the analysis will have something to read.",
			})
			return
		}

		// The answer only changes when the figures do, so an unchanged ledger
		// reuses the last one instead of paying for the same reply twice.
		if r.URL.Query().Get("refresh") != "1" {
			if text, at, ok := cache.get(digest); ok {
				writeJSON(w, http.StatusOK, map[string]any{
					"available":    true,
					"text":         text,
					"model":        geminiModel(),
					"generated_at": at.Format(time.RFC3339),
					"cached":       true,
				})
				return
			}
		}

		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()

		text, err := callGemini(ctx, apiKey, geminiModel(), fmt.Sprintf(insightPrompt, digest))
		if err != nil {
			writeJSON(w, http.StatusOK, map[string]any{
				"available": false,
				"reason":    err.Error(),
			})
			return
		}

		now := time.Now()
		cache.put(digest, text, now)
		writeJSON(w, http.StatusOK, map[string]any{
			"available":    true,
			"text":         text,
			"model":        geminiModel(),
			"generated_at": now.Format(time.RFC3339),
			"cached":       false,
		})
	})
}
