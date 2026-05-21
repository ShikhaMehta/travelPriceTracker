#!/usr/bin/env python3
"""
travelPriceTracker
Checks flight + hotel + Airbnb prices and emails you when the total drops below your threshold.
"""

import os
import sys
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# ─── Config from environment ───────────────────────────────────────────────────
AMADEUS_API_KEY     = os.getenv("AMADEUS_API_KEY")
AMADEUS_API_SECRET  = os.getenv("AMADEUS_API_SECRET")
RAPIDAPI_KEY        = os.getenv("RAPIDAPI_KEY")
GMAIL_SENDER        = os.getenv("GMAIL_SENDER")
GMAIL_APP_PASSWORD  = os.getenv("GMAIL_APP_PASSWORD")
GMAIL_RECIPIENT     = os.getenv("GMAIL_RECIPIENT")

AMADEUS_AUTH_URL    = "https://test.api.amadeus.com/v1/security/oauth2/token"
AMADEUS_FLIGHTS_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
AMADEUS_HOTELS_URL  = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
AMADEUS_CITY_URL    = "https://test.api.amadeus.com/v1/reference-data/locations/cities"
AIRBNB_URL          = "https://airbnb13.p.rapidapi.com/search-location"


# ─── Amadeus auth ──────────────────────────────────────────────────────────────
def get_amadeus_token():
    resp = requests.post(AMADEUS_AUTH_URL, data={
        "grant_type":    "client_credentials",
        "client_id":     AMADEUS_API_KEY,
        "client_secret": AMADEUS_API_SECRET,
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


# ─── IATA code lookup ──────────────────────────────────────────────────────────
def get_iata_code(city_name: str, token: str) -> str:
    """Try to resolve a city name to an IATA airport code."""
    resp = requests.get(AMADEUS_CITY_URL, headers={"Authorization": f"Bearer {token}"},
                        params={"keyword": city_name, "max": 1})
    data = resp.json()
    if resp.ok and data.get("data"):
        iata = data["data"][0].get("iataCode")
        if iata:
            return iata
    # Fallback: treat the input as a raw IATA code
    return city_name.strip().upper()


# ─── Flights ───────────────────────────────────────────────────────────────────
def get_cheapest_flight(origin: str, destination: str, depart_date: str,
                         return_date: str, adults: int, token: str) -> dict | None:
    params = {
        "originLocationCode":      origin,
        "destinationLocationCode": destination,
        "departureDate":           depart_date,
        "adults":                  adults,
        "currencyCode":            "USD",
        "max":                     5,
    }
    if return_date:
        params["returnDate"] = return_date

    resp = requests.get(AMADEUS_FLIGHTS_URL,
                        headers={"Authorization": f"Bearer {token}"},
                        params=params)
    data = resp.json()
    if not resp.ok or not data.get("data"):
        print(f"  [flights] No results or error: {data.get('errors', data)}")
        return None

    offers = sorted(data["data"], key=lambda x: float(x["price"]["grandTotal"]))
    best   = offers[0]
    return {
        "price":    float(best["price"]["grandTotal"]),
        "currency": best["price"]["currency"],
        "airline":  best["validatingAirlineCodes"][0] if best.get("validatingAirlineCodes") else "N/A",
        "stops":    best["itineraries"][0]["segments"][0].get("numberOfStops", 0),
    }


# ─── Hotels (Amadeus) ──────────────────────────────────────────────────────────
def get_cheapest_hotel(destination: str, checkin: str, checkout: str,
                        adults: int, token: str) -> dict | None:
    # Step 1: get hotel IDs near the city
    hotel_list_url = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
    r = requests.get(hotel_list_url,
                     headers={"Authorization": f"Bearer {token}"},
                     params={"cityCode": destination, "radius": 5, "radiusUnit": "KM", "ratings": "3,4,5"})
    if not r.ok or not r.json().get("data"):
        print(f"  [hotels] Could not find hotels for {destination}")
        return None

    hotel_ids = [h["hotelId"] for h in r.json()["data"][:20]]

    # Step 2: get offers
    resp = requests.get(AMADEUS_HOTELS_URL,
                        headers={"Authorization": f"Bearer {token}"},
                        params={
                            "hotelIds":   ",".join(hotel_ids),
                            "checkInDate":  checkin,
                            "checkOutDate": checkout,
                            "adults":       adults,
                            "currencyCode": "USD",
                            "bestRateOnly": True,
                        })
    data = resp.json()
    if not resp.ok or not data.get("data"):
        print(f"  [hotels] No offers: {data.get('errors', data)}")
        return None

    # Find cheapest available offer
    best_price = None
    best_name  = None
    for hotel in data["data"]:
        for offer in hotel.get("offers", []):
            try:
                price = float(offer["price"]["total"])
                if best_price is None or price < best_price:
                    best_price = price
                    best_name  = hotel["hotel"].get("name", "Unknown Hotel")
            except (KeyError, ValueError):
                continue

    if best_price is None:
        return None
    return {"price": best_price, "name": best_name, "currency": "USD"}


# ─── Airbnb (RapidAPI) ────────────────────────────────────────────────────────
def get_cheapest_airbnb(destination: str, checkin: str, checkout: str,
                         adults: int) -> dict | None:
    headers = {
        "X-RapidAPI-Key":  RAPIDAPI_KEY,
        "X-RapidAPI-Host": "airbnb13.p.rapidapi.com",
    }
    params = {
        "location":    destination,
        "checkin":     checkin,
        "checkout":    checkout,
        "adults":      adults,
        "children":    0,
        "infants":     0,
        "pets":        0,
        "page":        1,
        "currency":    "USD",
    }
    resp = requests.get(AIRBNB_URL, headers=headers, params=params)
    data = resp.json()
    if not resp.ok or not data.get("results"):
        print(f"  [airbnb] No results or error: {data.get('error', resp.status_code)}")
        return None

    results = data["results"]
    cheapest = min(results, key=lambda x: x.get("price", {}).get("total", float("inf")))
    total    = cheapest.get("price", {}).get("total")
    name     = cheapest.get("name", "Unknown Airbnb")
    url      = cheapest.get("url", "")

    if total is None:
        return None
    return {"price": float(total), "name": name, "url": url}


# ─── Email ─────────────────────────────────────────────────────────────────────
def send_alert(subject: str, body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = GMAIL_RECIPIENT
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_SENDER, GMAIL_RECIPIENT, msg.as_string())
    print("  [email] Alert sent!")


# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  travelPriceTracker")
    print("=" * 60)

    # ── Gather inputs ──────────────────────────────────────────
    origin      = input("Origin city or airport code (e.g. DFW or Dallas): ").strip()
    destination = input("Destination city or airport code (e.g. JFK or New York): ").strip()
    depart_date = input("Departure date (YYYY-MM-DD): ").strip()
    return_date = input("Return date (YYYY-MM-DD, or leave blank for one-way): ").strip()
    checkin     = depart_date
    checkout    = return_date if return_date else depart_date

    adults_str  = input("Number of adults [1]: ").strip()
    adults      = int(adults_str) if adults_str.isdigit() else 1

    lodging     = input("Lodging type — hotel, airbnb, or both [both]: ").strip().lower() or "both"
    threshold   = float(input("Price alert threshold in USD (total trip): ").strip())

    print("\nChecking prices...\n")

    # ── Amadeus token ──────────────────────────────────────────
    try:
        token = get_amadeus_token()
    except Exception as e:
        print(f"[ERROR] Could not authenticate with Amadeus: {e}")
        sys.exit(1)

    # ── Resolve IATA codes ─────────────────────────────────────
    origin_code = get_iata_code(origin, token)
    dest_code   = get_iata_code(destination, token)
    print(f"  Resolved: {origin} → {origin_code}, {destination} → {dest_code}")

    # ── Flights ────────────────────────────────────────────────
    print("\n[Flights]")
    flight = get_cheapest_flight(origin_code, dest_code, depart_date,
                                  return_date, adults, token)
    if flight:
        print(f"  Cheapest flight: ${flight['price']:.2f} ({flight['airline']})")
    else:
        print("  No flights found.")
        flight = {"price": 0}

    # ── Lodging ────────────────────────────────────────────────
    hotel  = None
    airbnb = None

    if lodging in ("hotel", "both"):
        print("\n[Hotels]")
        hotel = get_cheapest_hotel(dest_code, checkin, checkout, adults, token)
        if hotel:
            print(f"  Cheapest hotel: ${hotel['price']:.2f} — {hotel['name']}")
        else:
            print("  No hotels found.")

    if lodging in ("airbnb", "both"):
        print("\n[Airbnb]")
        airbnb = get_cheapest_airbnb(destination, checkin, checkout, adults)
        if airbnb:
            print(f"  Cheapest Airbnb: ${airbnb['price']:.2f} — {airbnb['name']}")
        else:
            print("  No Airbnb listings found.")

    # ── Pick cheapest lodging option ───────────────────────────
    options = [(h["price"], "Hotel",  h) for h in [hotel]  if h] + \
              [(a["price"], "Airbnb", a) for a in [airbnb] if a]

    if not options:
        print("\n[RESULT] No lodging found. Cannot calculate total.")
        sys.exit(0)

    best_lodging_price, best_lodging_type, best_lodging = min(options, key=lambda x: x[0])
    total = flight["price"] + best_lodging_price

    print(f"\n{'='*60}")
    print(f"  TOTAL (flight + {best_lodging_type}): ${total:.2f}")
    print(f"  Your threshold:                   ${threshold:.2f}")
    print(f"{'='*60}")

    # ── Alert check ────────────────────────────────────────────
    if total <= threshold:
        print(f"\n  *** DEAL FOUND! Total ${total:.2f} is under your ${threshold:.2f} threshold ***")

        lodging_detail = best_lodging.get("name", "")
        if best_lodging_type == "Airbnb" and best_lodging.get("url"):
            lodging_detail += f"\n  Link: {best_lodging['url']}"

        body = f"""
Travel Price Alert — Deal Found!

Route:        {origin} → {destination}
Dates:        {depart_date} to {checkout}
Adults:       {adults}

Flight:       ${flight['price']:.2f}  ({flight.get('airline','N/A')})
{best_lodging_type}:       ${best_lodging_price:.2f}  {lodging_detail}

TOTAL:        ${total:.2f}
Threshold:    ${threshold:.2f}

Book now before the price goes back up!
        """.strip()

        try:
            send_alert(f"Travel Deal: {origin} → {destination} for ${total:.2f}!", body)
        except Exception as e:
            print(f"  [ERROR] Could not send email: {e}")
            print("\n  --- Email body (copy manually) ---")
            print(body)
    else:
        print(f"\n  No deal yet. Total ${total:.2f} is above your ${threshold:.2f} threshold.")
        print("  Run this script again later, or lower your threshold.")


if __name__ == "__main__":
    main()
