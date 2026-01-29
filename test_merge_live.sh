#!/bin/bash

SESSION_ID="merge-test-$(date +%s)"
BASE_URL="https://red-spire-data.onrender.com"

echo "Testing session merging on live server..."
echo "Session ID: $SESSION_ID"
echo

# First submission
echo "1. First submission (submit 'hello'):"
RESPONSE1=$(curl -s -X POST "$BASE_URL/api/v1/keystroke/collect" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"user_id\": \"test-merge-user\",
    \"document_text\": \"hello\",
    \"events\": [
      {\"eventType\": \"keypress\", \"key\": \"h\", \"keyCode\": 72, \"timestamp\": \"2026-01-29T12:00:00Z\", \"sequence\": 1},
      {\"eventType\": \"keypress\", \"key\": \"e\", \"keyCode\": 69, \"timestamp\": \"2026-01-29T12:00:00.05Z\", \"sequence\": 2},
      {\"eventType\": \"keypress\", \"key\": \"l\", \"keyCode\": 76, \"timestamp\": \"2026-01-29T12:00:00.1Z\", \"sequence\": 3},
      {\"eventType\": \"keypress\", \"key\": \"l\", \"keyCode\": 76, \"timestamp\": \"2026-01-29T12:00:00.15Z\", \"sequence\": 4},
      {\"eventType\": \"keypress\", \"key\": \"o\", \"keyCode\": 79, \"timestamp\": \"2026-01-29T12:00:00.2Z\", \"sequence\": 5}
    ]
  }")

echo "$RESPONSE1" | python3 -m json.tool
PROB1=$(echo "$RESPONSE1" | python3 -c "import sys, json; print(json.load(sys.stdin)['human_probability'])" 2>/dev/null || echo "ERROR")
echo "Human Probability: $PROB1"
echo

# Second submission
echo "2. Second submission (add ' world' to same session):"
RESPONSE2=$(curl -s -X POST "$BASE_URL/api/v1/keystroke/collect" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"user_id\": \"test-merge-user\",
    \"document_text\": \"hello world\",
    \"events\": [
      {\"eventType\": \"keypress\", \"key\": \" \", \"keyCode\": 32, \"timestamp\": \"2026-01-29T12:00:00.25Z\", \"sequence\": 6},
      {\"eventType\": \"keypress\", \"key\": \"w\", \"keyCode\": 87, \"timestamp\": \"2026-01-29T12:00:00.3Z\", \"sequence\": 7},
      {\"eventType\": \"keypress\", \"key\": \"o\", \"keyCode\": 79, \"timestamp\": \"2026-01-29T12:00:00.35Z\", \"sequence\": 8},
      {\"eventType\": \"keypress\", \"key\": \"r\", \"keyCode\": 82, \"timestamp\": \"2026-01-29T12:00:00.4Z\", \"sequence\": 9},
      {\"eventType\": \"keypress\", \"key\": \"l\", \"keyCode\": 76, \"timestamp\": \"2026-01-29T12:00:00.45Z\", \"sequence\": 10},
      {\"eventType\": \"keypress\", \"key\": \"d\", \"keyCode\": 68, \"timestamp\": \"2026-01-29T12:00:00.5Z\", \"sequence\": 11}
    ]
  }")

echo "$RESPONSE2" | python3 -m json.tool
PROB2=$(echo "$RESPONSE2" | python3 -c "import sys, json; print(json.load(sys.stdin)['human_probability'])" 2>/dev/null || echo "ERROR")
echo "Human Probability (merged): $PROB2"
echo

# Verify
echo "3. Verify merged session:"
curl -s -X POST "$BASE_URL/api/v1/keystroke/verify" \
  -H "Content-Type: application/json" \
  -d "{\"document_text\": \"hello world\"}" | python3 -m json.tool
