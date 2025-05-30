# Environment Variables Documentation

## Current Environment Variables
- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather
- `AIRTABLE_API_KEY`: Airtable Personal Access Token
- `AIRTABLE_BASE_ID`: Airtable Base ID
- `WEBHOOK_URL`: URL for Telegram webhook
- `PORT`: Port number for the server

## Service-Specific Variables

### Webhook Server
- `PORT`: Port for webhook server (default: 10000)
- `TELEGRAM_BOT_TOKEN`: For webhook verification
- `BOT_SERVICE_URL`: URL of the bot service for forwarding updates

### Telegram Bot Service
- `TELEGRAM_BOT_TOKEN`: For bot authentication
- `AIRTABLE_API_KEY`: For database access
- `AIRTABLE_BASE_ID`: For database access
- `USE_LONG_POLLING`: Set to "true" to use long polling instead of webhooks

## Migration Notes
1. Both services will need access to Airtable credentials
2. Webhook server needs minimal configuration
3. Bot service will handle all Telegram interactions
4. Consider using different ports for local development

## Security Considerations
1. Keep tokens secure
2. Use different tokens for development and production
3. Consider using a secrets manager for production
4. Rotate tokens regularly 