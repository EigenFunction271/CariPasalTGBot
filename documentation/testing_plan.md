# Testing Plan for Split Architecture

## 1. Local Testing Setup

### Environment Setup
```bash
# Create test environment variables
cp .env .env.test
# Modify .env.test with test values
```

### Required Test Variables
- `TELEGRAM_BOT_TOKEN`: Test bot token
- `BOT_SERVICE_URL`: Local bot service URL (e.g., http://localhost:10001)
- `AIRTABLE_API_KEY`: Test Airtable token
- `AIRTABLE_BASE_ID`: Test Airtable base
- `PORT`: Different ports for each service (e.g., 10000 for webhook, 10001 for bot)

## 2. Service Testing

### Bot Service Testing
1. Start bot service:
   ```bash
   cd services/telegram_bot
   python bot.py
   ```
2. Test commands:
   - `/start`
   - `/newproject`
   - `/myprojects`
   - `/cancel`
3. Verify:
   - Command responses
   - Airtable integration
   - Error handling
   - Logging

### Webhook Server Testing
1. Start webhook server:
   ```bash
   cd services/webhook_server
   gunicorn -c gunicorn_config.py app:app
   ```
2. Test endpoints:
   - `GET /health`
   - `POST /` (webhook)
3. Verify:
   - Health check response
   - Webhook forwarding
   - Error handling
   - Logging

## 3. Integration Testing

### End-to-End Flow
1. Set up ngrok for local testing:
   ```bash
   ngrok http 10000
   ```
2. Update webhook URL in Telegram:
   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=<NGROK_URL>
   ```
3. Test complete flows:
   - New project creation
   - Project updates
   - Project viewing
   - Error scenarios

### Error Scenarios
1. Bot service down
2. Webhook server down
3. Airtable connection issues
4. Invalid webhook data
5. Network timeouts

## 4. Performance Testing

### Load Testing
1. Use a tool like `locust` to simulate:
   - Multiple concurrent users
   - High message volume
   - Long-running conversations

### Monitoring
1. Check logs for:
   - Response times
   - Error rates
   - Resource usage
2. Verify:
   - No memory leaks
   - Stable CPU usage
   - Proper error handling

## 5. Security Testing

### Authentication
1. Verify token validation
2. Test invalid tokens
3. Check header validation

### Data Validation
1. Test malformed webhook data
2. Verify input sanitization
3. Check Airtable data integrity

## 6. Deployment Testing

### Render Setup
1. Create two services:
   - Webhook server
   - Bot service
2. Configure:
   - Environment variables
   - Build commands
   - Start commands
3. Test:
   - Service startup
   - Health checks
   - Logging
   - Monitoring

## Success Criteria
- All commands work as expected
- Webhook forwarding is reliable
- Error handling is robust
- Logging is comprehensive
- Performance is acceptable
- Security measures are effective

## Rollback Plan
1. Keep old code in separate branch
2. Document rollback steps
3. Test rollback procedure
4. Monitor after rollback 