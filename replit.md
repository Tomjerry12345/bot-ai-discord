# Toram Online Discord Bot

## Overview
A Discord bot for Toram Online Indonesia community that provides AI-powered Q&A functionality. Users can teach the bot about game information and ask questions.

## Project Structure
- `main.py` - Main bot application with all commands and logic
- `toram_knowledge.json` - Knowledge base storage (auto-created)
- `requirements.txt` - Python dependencies

## Required Secrets
- `DISCORD_TOKEN` - Discord bot token (required)
- `GROQ_API_KEY` - Groq API key for AI features (optional, but recommended)

## Commands
- `!tanya` / `!ask` / `!ai` / `!t` - Ask the AI helper
- `!teach` / `!ajari` / `!train` - Teach the bot new Q&A pairs
- `!search` / `!cari` / `!s` - Search the knowledge base
- `!list` - List all Q&A entries
- `!update` / `!edit` / `!ubah` - Update existing entries
- `!delete` / `!hapus` - Delete an entry (requires manage_messages permission)
- `!knowledge` / `!database` / `!db` / `!info` - View database stats
- `!importtxt` - Import Q&A from text file (admin only)
- `!help` - Show help

## Running the Bot
The bot runs as a console application. It requires a valid Discord token to connect.

## Recent Changes
- Initial import from GitHub (December 26, 2025)
