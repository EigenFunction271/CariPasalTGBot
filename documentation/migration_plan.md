# Service Migration Plan: Split Architecture

## Overview
This document outlines the plan to split the current monolithic service into two separate services:
1. Webhook Server (Flask)
2. Telegram Bot Service (asyncio)

## Current Architecture
- Single Flask application with Gunicorn
- Gevent monkey patching for asyncio integration
- Webhook-based Telegram updates
- Direct Airtable integration

## Target Architecture
```
/services
  /webhook_server
    - app.py (simplified Flask)
    - gunicorn_config.py (standard)
  /telegram_bot
    - bot.py (asyncio)
    - handlers/ (existing)
```

## Migration Steps

### Phase 1: Preparation
1. Create new directory structure
   ```bash
   mkdir -p services/{webhook_server,telegram_bot}
   ```

2. Set up version control
   - Create new branch: `feature/split-services`
   - Update .gitignore for new structure

3. Document current environment variables
   - List all required variables
   - Plan for service-specific variables

### Phase 2: Bot Service Migration
1. Create new `bot.py`
   - Move Telegram bot initialization
   - Set up asyncio event loop
   - Configure long polling

2. Migrate handlers
   - Move handlers directory to bot service
   - Update imports
   - Test handler functionality

3. Update database access
   - Ensure direct Airtable access
   - Test database operations

### Phase 3: Webhook Server Migration
1. Simplify `app.py`
   - Remove Telegram bot code
   - Keep only webhook endpoint
   - Add health check endpoint

2. Update Gunicorn config
   - Remove gevent monkey patching
   - Use standard worker class
   - Configure for webhook handling

3. Add service communication
   - Implement message forwarding
   - Add error handling
   - Set up logging

### Phase 4: Testing
1. Local testing
   - Test bot service independently
   - Test webhook server
   - Test end-to-end flow

2. Integration testing
   - Test Airtable integration
   - Test error handling
   - Test recovery scenarios

### Phase 5: Deployment
1. Render configuration
   - Create two services
   - Configure environment variables
   - Set up health checks

2. Monitoring setup
   - Configure logging
   - Set up alerts
   - Monitor both services

3. Rollout plan
   - Deploy bot service first
   - Deploy webhook server
   - Monitor for issues

## Rollback Plan
1. Keep old code in separate branch
2. Document rollback steps
3. Test rollback procedure

## Success Criteria
- Both services running independently
- No degradation in user experience
- Improved error handling
- Better monitoring capabilities

## Timeline
- Phase 1: 1 day
- Phase 2: 2-3 days
- Phase 3: 1-2 days
- Phase 4: 2-3 days
- Phase 5: 1-2 days

Total: 7-11 days

## Risks and Mitigations
1. **Service Communication**
   - Risk: Message loss between services
   - Mitigation: Implement retry logic

2. **Data Consistency**
   - Risk: Inconsistent state between services
   - Mitigation: Use Airtable as source of truth

3. **Deployment Issues**
   - Risk: Service downtime during migration
   - Mitigation: Deploy during low-usage period

4. **Performance**
   - Risk: Increased latency
   - Mitigation: Monitor and optimize

## Next Steps
1. Review and approve migration plan
2. Set up development environment
3. Begin Phase 1 implementation 