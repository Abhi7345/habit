# HabitFlow

HabitFlow is a multi-page habit tracker with a Python backend, static HTML frontend, and PostgreSQL storage that is now set up for Vercel deployment.

## What Changed For Vercel

- SQLite was replaced with PostgreSQL via `DATABASE_URL`
- In-memory sessions were replaced with database-backed sessions
- A Vercel Python function entrypoint was added at `api/index.py`
- Static files continue to be served directly by Vercel

## Required Environment Variables

- `DATABASE_URL`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

You can copy values from `.env.example` when setting up local or hosted environments.

## Run Locally

Set environment variables first:

```powershell
$env:DATABASE_URL="postgresql://username:password@host:5432/habitflow"
$env:ADMIN_USERNAME="abhi"
$env:ADMIN_PASSWORD="abhi"
py server.py
```

Then open:

- `http://127.0.0.1:8000`

## Deploy To Vercel

1. Push this project to GitHub
2. Create a PostgreSQL database on Neon, Supabase, Railway, Vercel Postgres, or another hosted provider
3. Copy the database connection string into `DATABASE_URL`
4. Import the GitHub repo into [Vercel](https://vercel.com/)
5. In the Vercel project settings, add:
   - `DATABASE_URL`
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
6. Deploy

Vercel uses:

- `vercel.json` for routing `/api/*` requests into the Python function
- `api/index.py` as the serverless backend entrypoint
- root HTML/CSS/JS files as static assets

## Important Notes

- `habitflow.db` is no longer used for production deployment
- User data and login sessions now live in PostgreSQL
- Admin credentials are controlled by environment variables instead of being hardcoded for deployment

## Main Files

- `habitflow_app.py`
- `api/index.py`
- `server.py`
- `vercel.json`
- `.env.example`
- `requirements.txt`
- `index.html`
- `user.html`
- `admin.html`
- `user-review.html`
- `admin-review.html`
