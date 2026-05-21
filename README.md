# travelPriceTracker

Checks flight + hotel/Airbnb prices and emails you when the **total trip cost** drops below your threshold.

---

## What You'll Need (all free tiers)

### 1. Amadeus API (flights + hotels)
1. Go to https://developers.amadeus.com and create a free account
2. Create a new app — you'll get an **API Key** and **API Secret**
3. The free "test" environment is enough to start

### 2. RapidAPI — Airbnb13 (Airbnb listings)
1. Go to https://rapidapi.com and create a free account
2. Search for **"Airbnb13"** and subscribe to the free tier
3. Your **RapidAPI Key** is shown in the API console under "Header Parameters"

### 3. Gmail App Password (for sending alert emails)
1. Go to https://myaccount.google.com/apppasswords
2. Sign in, select "Mail" and your device, click Generate
3. Copy the 16-character password — you won't see it again

---

## Setup

### Step 1 — Copy the env file
```bash
cp .env.example .env
```

### Step 2 — Fill in your keys
Open `.env` and replace every `your_*_here` placeholder with your real values:
```
AMADEUS_API_KEY=abc123...
AMADEUS_API_SECRET=xyz789...
RAPIDAPI_KEY=abc123...
GMAIL_SENDER=yourname@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_RECIPIENT=yourname@gmail.com
```

---

## Running with Docker (recommended)

### Build the image (one time)
```bash
docker build -t travelprice-tracker .
```

### Run it
```bash
docker run -it --env-file .env travelprice-tracker
```

The app will prompt you interactively:
```
Origin city or airport code (e.g. DFW or Dallas): Dallas
Destination city or airport code (e.g. JFK or New York): New York
Departure date (YYYY-MM-DD): 2026-07-04
Return date (YYYY-MM-DD, or leave blank for one-way): 2026-07-10
Number of adults [1]: 2
Lodging type — hotel, airbnb, or both [both]: both
Price alert threshold in USD (total trip): 1200
```

If the total is under your threshold, an email is sent automatically.

---

## Running without Docker (Python directly)

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python main.py
```

---

## How It Works

1. You enter your trip details and a price threshold
2. The app queries:
   - **Amadeus** for the cheapest available flight
   - **Amadeus** for the cheapest hotel near your destination
   - **Airbnb13 (RapidAPI)** for the cheapest Airbnb listing
3. It picks the cheaper lodging option and adds it to the flight cost
4. If the total is at or below your threshold → sends you an email alert
5. If not → tells you the current total so you know how close you are

---

## Tips

- **Run it on a schedule** — set up a Windows Task Scheduler job or cron job to run the Docker container daily
- **One-way trips** — leave the return date blank
- **Hotels only** — type `hotel` at the lodging prompt to skip Airbnb
- **Airbnb only** — type `airbnb` to skip hotels

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Could not authenticate with Amadeus` | Double-check `AMADEUS_API_KEY` and `AMADEUS_API_SECRET` in `.env` |
| `No flights found` | Try using the 3-letter IATA code directly (e.g. `DFW`, `JFK`) |
| `No Airbnb results` | Check your `RAPIDAPI_KEY` and make sure you subscribed to Airbnb13 |
| Email not sending | Make sure you're using a Gmail **App Password**, not your real password |
| `[ERROR] Could not send email` | The email body is printed to the console so you don't lose the deal |
