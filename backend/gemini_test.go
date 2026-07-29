package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestExtractText(t *testing.T) {
	textResponse := func(parts ...string) geminiResponse {
		var r geminiResponse
		p := make([]geminiPart, 0, len(parts))
		for _, s := range parts {
			p = append(p, geminiPart{Text: s})
		}
		r.Candidates = append(r.Candidates, struct {
			Content      geminiContent `json:"content"`
			FinishReason string        `json:"finishReason"`
		}{Content: geminiContent{Parts: p}})
		return r
	}

	t.Run("joins the parts of a reply", func(t *testing.T) {
		got, err := extractText(textResponse("Food is up 18%. ", "Cut two takeaways a week."))
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got != "Food is up 18%. Cut two takeaways a week." {
			t.Errorf("got %q", got)
		}
	})

	t.Run("reports an API error", func(t *testing.T) {
		var r geminiResponse
		r.Error.Message = "API key not valid"
		if _, err := extractText(r); err == nil || !strings.Contains(err.Error(), "API key not valid") {
			t.Errorf("expected the API message to surface, got %v", err)
		}
	})

	t.Run("reports a blocked prompt", func(t *testing.T) {
		var r geminiResponse
		r.PromptFeedback.BlockReason = "SAFETY"
		if _, err := extractText(r); err == nil || !strings.Contains(err.Error(), "SAFETY") {
			t.Errorf("expected the block reason to surface, got %v", err)
		}
	})

	t.Run("reports no candidates", func(t *testing.T) {
		if _, err := extractText(geminiResponse{}); err == nil {
			t.Error("expected an error when there are no candidates")
		}
	})

	// A reply that is all whitespace is a failure, not an analysis — this is
	// what a model returns when the token budget went on reasoning.
	t.Run("reports an empty reply", func(t *testing.T) {
		if _, err := extractText(textResponse("   ")); err == nil {
			t.Error("expected an error for an empty reply")
		}
	})
}

func TestLoadDotEnv(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, ".env")
	contents := strings.Join([]string{
		"# a comment",
		"",
		"GEMINI_API_KEY=from-file",
		`QUOTED="quoted-value"`,
		"  SPACED  =  padded  ",
		"ALREADY_SET=from-file",
		"malformed-line-without-equals",
	}, "\n")
	if err := os.WriteFile(path, []byte(contents), 0o600); err != nil {
		t.Fatalf("writing .env: %v", err)
	}

	t.Setenv("ALREADY_SET", "from-environment")
	t.Setenv("GEMINI_API_KEY", "")
	os.Unsetenv("GEMINI_API_KEY")

	loadDotEnv(path)

	if got := os.Getenv("GEMINI_API_KEY"); got != "from-file" {
		t.Errorf("GEMINI_API_KEY: got %q, want %q", got, "from-file")
	}
	if got := os.Getenv("QUOTED"); got != "quoted-value" {
		t.Errorf("QUOTED: got %q, want %q", got, "quoted-value")
	}
	if got := os.Getenv("SPACED"); got != "padded" {
		t.Errorf("SPACED: got %q, want %q", got, "padded")
	}
	// An exported variable is the more deliberate choice, so the file must not
	// overwrite it.
	if got := os.Getenv("ALREADY_SET"); got != "from-environment" {
		t.Errorf("ALREADY_SET: got %q, want the existing environment value", got)
	}
}

func TestLoadDotEnv_MissingFileIsFine(t *testing.T) {
	loadDotEnv(filepath.Join(t.TempDir(), "does-not-exist"))
}

func TestInsightCache(t *testing.T) {
	c := &insightCache{}
	at := time.Now()

	if _, _, ok := c.get("digest-a"); ok {
		t.Error("empty cache should miss")
	}

	c.put("digest-a", "the analysis", at)
	text, when, ok := c.get("digest-a")
	if !ok || text != "the analysis" || !when.Equal(at) {
		t.Errorf("expected a hit for the stored digest, got %q %v %v", text, when, ok)
	}
	// Different figures must not serve the previous answer.
	if _, _, ok := c.get("digest-b"); ok {
		t.Error("a changed digest should miss")
	}
}

func TestSpendingDigest(t *testing.T) {
	db, err := InitDB(filepath.Join(t.TempDir(), "digest.db"))
	if err != nil {
		t.Fatalf("InitDB: %v", err)
	}
	defer db.Close()

	digest, hasSpending, err := spendingDigest(db, date("2026-07-29"))
	if err != nil {
		t.Fatalf("spendingDigest: %v", err)
	}
	if hasSpending {
		t.Error("an empty ledger should report no spending, so no API call is made")
	}
	if !strings.Contains(digest, "(nothing recorded)") {
		t.Errorf("expected the empty ledger to say so, got:\n%s", digest)
	}

	if _, err := db.Exec(
		"INSERT INTO expenses (amount, category_id, date, note) VALUES (42.5, 1, '2026-07-04', 'lunch with Sam')",
	); err != nil {
		t.Fatalf("inserting expense: %v", err)
	}
	if _, err := db.Exec(
		"INSERT INTO income (amount, source, date) VALUES (4200, 'Salary', '2026-07-01')",
	); err != nil {
		t.Fatalf("inserting income: %v", err)
	}

	digest, hasSpending, err = spendingDigest(db, date("2026-07-29"))
	if err != nil {
		t.Fatalf("spendingDigest: %v", err)
	}
	if !hasSpending {
		t.Error("expected recorded spending to be reported")
	}
	if !strings.Contains(digest, "42.50") {
		t.Errorf("expected the expense total in the digest, got:\n%s", digest)
	}
	if !strings.Contains(digest, "4200.00") {
		t.Errorf("expected the income total in the digest, got:\n%s", digest)
	}
	// Notes are free text and can hold anything personal; only aggregates and
	// category names are sent off the machine.
	if strings.Contains(digest, "lunch with Sam") {
		t.Errorf("expense notes must not be sent to the API, got:\n%s", digest)
	}
}
