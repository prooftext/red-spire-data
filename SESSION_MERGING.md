# Session Merging Feature

## Overview
Clients can now send keystroke data to the same session in multiple requests. When a session ID is repeated, the system intelligently merges the new keystroke events with the existing session while updating metrics and human probability calculations.

## How It Works

### Architecture
1. **Session Check**: When `/api/v1/keystroke/collect` receives a request, it checks if the session already exists
2. **Conditional Action**:
   - **New Session**: Creates a fresh session if the session_id doesn't exist
   - **Existing Session**: Updates the existing session with new metrics based on merged keystroke data
3. **Event Storage**: New keystroke events are appended to the session's event history
4. **Metrics Recalculation**: Human probability and verification status are recalculated based on all events (original + new)

### Database Updates
- **Session Record**: Updated with new `session_end`, `total_duration_ms`, `human_probability`, `verification_status`, and `session_metrics`
- **Keystroke Events**: New events are inserted with sequential numbering
- **Full-Text Search**: Document index (`document_tsvector`) remains updated for verification queries

## API Usage Example

### First Submission
```json
POST /api/v1/keystroke/collect
{
  "session_id": "user-session-001",
  "user_id": "user@example.com",
  "document_text": "hello",
  "events": [
    {"eventType": "keypress", "key": "h", "timestamp": "2026-01-29T12:00:00Z", "sequence": 1},
    {"eventType": "keypress", "key": "e", "timestamp": "2026-01-29T12:00:00.05Z", "sequence": 2},
    {"eventType": "keypress", "key": "l", "timestamp": "2026-01-29T12:00:00.1Z", "sequence": 3}
  ]
}

Response: 
{
  "session_id": "user-session-001",
  "human_probability": 0.82,
  "verification_status": "yes",
  "metrics": { ... }
}
```

### Second Submission (Same Session)
```json
POST /api/v1/keystroke/collect
{
  "session_id": "user-session-001",  // Same session ID
  "user_id": "user@example.com",
  "document_text": "hello world",     // Updated/extended document
  "events": [
    {"eventType": "keypress", "key": " ", "timestamp": "2026-01-29T12:00:00.2Z", "sequence": 4},
    {"eventType": "keypress", "key": "w", "timestamp": "2026-01-29T12:00:00.25Z", "sequence": 5},
    {"eventType": "keypress", "key": "o", "timestamp": "2026-01-29T12:00:00.3Z", "sequence": 6}
  ]
}

Response:
{
  "session_id": "user-session-001",  // Same session
  "human_probability": 0.79,          // Recalculated with all 6 events
  "verification_status": "yes",       // Updated status
  "metrics": { ... }                  // Merged metrics
}
```

## Implementation Details

### Code Changes
1. **app/repositories/sessions.py**:
   - Added `session_exists()`: Checks if session_id already exists in database
   - Added `create_or_merge_session()`: Handles both create and update logic
   - Maintained `create_session()` as legacy wrapper for backward compatibility

2. **app/routers/collect.py**:
   - Updated to use `create_or_merge_session()` instead of `create_session()`
   - No changes to endpoint logic or request/response formats

3. **Database Schema**:
   - No schema changes needed
   - Existing `typing_sessions` table structure supports updates
   - Existing `keystroke_events` table supports multiple event insertions

### Tests
New test added: `test_collect_merges_multiple_submissions_to_same_session`
- Verifies first submission creates session
- Verifies second submission to same session_id updates existing record
- Confirms metrics are recalculated
- Verifies human_probability reflects merged behavior

**Test Results**: All 17 tests pass (including 6 new tests from this session)

## Behavior Notes

### Session Duration
- **First Submission**: Duration calculated from first event timestamp to last event timestamp
- **Subsequent Submissions**: Duration extended to include new events' timestamps
- Example: 
  - First: 0ms-300ms (3 events over 300ms) = 300ms total
  - Second: 0ms-600ms (6 events over 600ms) = 600ms total (extended)

### Metrics Recalculation
- **Keystroke Count**: Sums all events from original + new submissions
- **Average Dwell Time**: Averaged across all events
- **Paste Detection**: Any paste events across all submissions flag the session
- **Correction Count**: Backspace/deletion events from all submissions counted

### Verification Behavior
- Sessions can be verified at any point with `POST /api/v1/keystroke/verify`
- Verification searches based on final merged `document_text`
- All keystroke events (original + merged) are used for human probability calculation

## Benefits
1. **Mobile/Low-Bandwidth Support**: Clients can send keystrokes in chunks instead of waiting for complete sentences
2. **Error Recovery**: If a submission fails, client can retry without losing previous data
3. **Long Sessions**: Multi-part documents can be submitted incrementally
4. **Flexible Clients**: No requirement for clients to batch all events before sending

## Backward Compatibility
✓ Fully backward compatible
- Existing single-submission code works unchanged
- New merging only activates for repeated session IDs
- API request/response formats identical
- No database migrations required
