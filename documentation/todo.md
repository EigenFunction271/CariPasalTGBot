# TODO List: Loophole Hackers Telegram Bot Improvements

## 1. Input Validation
- [ ] Apply `validate_input` to all user inputs (tagline, problem_statement, tech_stack, github_link, progress, blockers)
- [ ] Add URL validation for GitHub/Demo links
- [ ] Add a fallback handler for non-text messages in conversations

## 2. Error Handling & User Feedback
- [ ] Log errors in `get_user_projects` and `get_project_updates` and send user-friendly error messages if data cannot be fetched
- [ ] Use `.get()` for all Airtable field accesses, with sensible defaults, to avoid KeyError
- [ ] Add more specific error messages for common user-facing errors

## 3. User Data Management
- [ ] Ensure `context.user_data.clear()` is called on all conversation exits, including early returns and errors

## 4. Airtable Pagination & Rate Limiting
- [ ] Implement pagination for large Airtable queries (fetch in batches, limit results shown to user)
- [ ] Add basic handling for Airtable rate limits (catch HTTP 429, retry with backoff)

## 5. Webhook Management
- [ ] Before setting the webhook, check if it's already set to the correct URL to avoid redundant API calls

## 6. Async Handling
- [ ] (Optional, advanced) Consider migrating to an async web server (e.g., Quart or FastAPI) for better concurrency, or document the limitations of using `asyncio.run()` in Flask

## 7. Schema Change Resilience
- [ ] Add startup-time schema validation or logging for missing fields in Airtable 