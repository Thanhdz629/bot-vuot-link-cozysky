# Overview

This is a Discord bot integrated with a Flask web server and YeuMoney payment service. The bot manages a virtual currency system ("xu") where users can earn rewards by completing YeuMoney link visits and redeem codes for currency. The system includes:

- Discord bot with slash commands for claiming, redeeming, and withdrawing virtual currency
- Flask web server to display redemption codes and handle callback URLs
- YeuMoney API integration for generating payment/visit links
- Automated code generation system to maintain a pool of redeemable codes
- Per-user tracking of currency balances, transaction logs, and daily claim limits
- Ngrok tunneling to expose local web server for external redirects

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Bot Framework
- **Discord.py** with slash commands (`app_commands`) for modern Discord interaction patterns
- Single-file bot architecture (`main.py`) combining Discord bot, Flask server, and business logic
- Threading model: Flask runs in a separate daemon thread to allow concurrent Discord bot operation

## Virtual Currency System
- **Per-user JSON storage** in `data/<user_id>.json` containing:
  - Current balance (`xu`)
  - Transaction logs with timestamps and descriptions
  - Daily claim tracking (`last_day`, `claims_today`)
- **Daily claim limits** (configurable via `DAILY_LIMIT`) reset automatically at day boundary
- **Three-file state management**:
  - `codes.json`: Pool of available redeemable codes
  - `pending.json`: Active redemption sessions awaiting completion
  - `used.json`: Historical record of all redeemed codes

## Code Generation & Redemption Flow
- **Automatic replenishment**: `gen_code.py` generates new 8-character alphanumeric codes when pool drops below threshold (10 codes)
- **Two-step redemption process**:
  1. User requests code via `/nhanxu` → creates YeuMoney link with unique token
  2. User completes link visit → returns to Flask route → code is marked redeemed → currency awarded
- **Expiration mechanism**: Pending redemptions expire after configurable timeout (default 600 seconds)
- **Token-based tracking**: UUID tokens prevent replay attacks and link redemption sessions to users

## Web Server Architecture
- **Flask minimal server** with two routes:
  - `/<code>`: Displays redemption page with user's code
  - Callback handling for YeuMoney redirects (token validation)
- **Ngrok integration** for public URL generation:
  - Automatically configures tunnel on startup if `NGROK_AUTH_TOKEN` provided
  - Updates `WEB_BASE` environment variable with public URL
  - Required for YeuMoney service to redirect users back to application

## Discord Bot Commands
- **User commands**:
  - `/nhanxu`: Request new redemption code (respects daily limits)
  - `/rutxu`: Withdraw currency to designated channel with custom username
  - `/xemxu`: Check current balance
- **Admin commands** (restricted by `ADMIN_IDS`):
  - `/setxu`: Directly set user balance
  - `/addxu`: Add currency to user balance
  - `/admin_rutxu`: Withdraw currency on behalf of another user

## Data Persistence
- **JSON file-based storage** (no database):
  - Simple, human-readable format
  - Atomic writes with file locking considerations
  - Each user has isolated JSON file for balance/logs
- **Append-only logs**: Transaction history preserved in user files for audit trail

## Configuration Management
- **Environment variables** via `.env` file:
  - Discord bot token (`DISCORD_TOKEN`)
  - YeuMoney API token (`YEUMONEY_TOKEN`)
  - Ngrok auth token (`NGROK_AUTH_TOKEN`)
  - Channel IDs, admin user IDs, reward amounts, limits
- **Hot-reload not supported**: Configuration changes require bot restart

# External Dependencies

## Third-Party Services
- **Discord API**: Bot hosting platform and primary user interface
  - Uses discord.py library for API interaction
  - Requires bot token from Discord Developer Portal
  - Slash command registration via `app_commands`

- **YeuMoney** (yeumoney.com): Link shortening/monetization service
  - API endpoint: `https://yeumoney.com/QL_api.php`
  - Provides link generation for reward distribution
  - Returns shortened links that redirect to specified callback URLs
  - Requires API token for authentication

- **Ngrok**: HTTP tunneling service
  - Creates public HTTPS URLs for local Flask server
  - Essential for receiving callbacks from YeuMoney
  - Requires free account and auth token
  - Library: `pyngrok`

## Python Libraries
- **discord.py**: Discord bot framework
- **Flask**: Lightweight web framework for code display pages
- **python-dotenv**: Environment variable management
- **requests**: HTTP client for YeuMoney API calls
- **pyngrok**: Python wrapper for ngrok tunneling

## File System Dependencies
- Requires write access to:
  - `codes.json`, `pending.json`, `used.json` (state files)
  - `data/` directory for per-user JSON files
  - `.env` for configuration (optional, uses environment variables otherwise)

## Deployment Considerations
- **Replit environment**: Designed to run on Replit with Secrets management
- **Port binding**: Configurable via `PORT` environment variable (default 5000)
- **No database required**: Completely file-based for simplicity on lightweight hosting