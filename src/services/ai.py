import os
import random
import urllib.parse
import logging
from src.services.ai_provider import ai_provider

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # OpenAI client initialization is completely removed
        pass

    async def generate_chat_response(self, message: str, history: list = None) -> str:
        """
        Generates a context-aware travel planning response using the free AI provider fallback chain.
        """
        system_instruction = "You are TripSync AI, a premium, intelligent, context-aware travel companion assistant. You specialize in travel planning, route optimization, group travel budgets, hidden gems, and destination safety. Provide helpful, structured, concise travel recommendations with emojis and markdown formatting."
        
        try:
            reply = await ai_provider.generate_text(
                system_instruction=system_instruction,
                prompt=message,
                history=history,
                force_json=False
            )
            if reply:
                return reply
        except Exception as e:
            logger.error("Free AI provider chain failed: %s. Running local fallback.", e)

        return self._generate_sophisticated_fallback(message)

    async def generate_voice_briefing(self, data: dict) -> str:
        """
        Generates a natural, spoken travel briefing based on user active/upcoming trips,
        group activities, weather conditions, and traffic advisories using free AI models.
        """
        user_name = data.get("userName", "Traveler")
        active_trip_name = data.get("activeTripName")
        active_trip_dest = data.get("activeTripDestination")
        today_schedule_title = data.get("todayScheduleTitle")
        today_schedule_spots = data.get("todayScheduleSpots", [])
        upcoming_trip_name = data.get("upcomingTripName")
        upcoming_trip_dest = data.get("upcomingTripDestination")
        upcoming_trip_days = data.get("upcomingTripDays")
        group_name = data.get("groupName")
        group_expenses_count = data.get("groupExpensesCount", 0)
        group_last_expense_amount = data.get("groupLastExpenseAmount", 0.0)
        group_last_expense_desc = data.get("groupLastExpenseDesc")
        weather_temp = data.get("weatherTemp")
        weather_desc = data.get("weatherDesc")

        prompt = f"""Generate a short, friendly, spoken travel briefing for {user_name}.
Context:
- Active Trip: {active_trip_name} in {active_trip_dest}
- Today's Plan: {today_schedule_title}
- Stops to visit today: {', '.join(today_schedule_spots) if today_schedule_spots else 'none'}
- Upcoming Trip: {upcoming_trip_name} to {upcoming_trip_dest} starting in {upcoming_trip_days} days
- Group Expense Update: Group {group_name} has {group_expenses_count} expenses, last added was {group_last_expense_amount} for {group_last_expense_desc}
- Weather: {weather_temp}°C, {weather_desc}
- Traffic: Moderate delays near main destinations.

Write a natural speech script (3-4 sentences max) that can be read aloud. Start with a greeting based on the current time (e.g. 'Good morning' or 'Hello'). Keep it conversational and brief. Avoid markdown, bullet points, asterisks or special character symbols."""

        system_instruction = "You are a warm, professional voice assistant for TripSync. Speak directly to the user in a natural, smooth, concise way. Do not output markdown, bullet points, or special characters. Use plain text only, suitable for text-to-speech engines."

        try:
            briefing = await ai_provider.generate_text(
                system_instruction=system_instruction,
                prompt=prompt,
                force_json=False
            )
            if briefing:
                return briefing.strip().replace("*", "").replace("#", "")
        except Exception as e:
            logger.error("Free AI voice briefing failed: %s. Running local fallback.", e)

        # Highly dynamic local fallback generation
        from datetime import datetime
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        
        briefing_parts = [f"{greeting} {user_name}."]

        if active_trip_name and active_trip_dest:
            briefing_parts.append(f"Today you have your {active_trip_name} in {active_trip_dest} active.")
            if today_schedule_title:
                briefing_parts.append(f"Your schedule is {today_schedule_title}.")
            if today_schedule_spots:
                briefing_parts.append(f"Your first destination is {today_schedule_spots[0]}. Traffic nearby is currently moderate.")
        elif upcoming_trip_name and upcoming_trip_dest:
            briefing_parts.append(f"You don't have an active trip today, but your upcoming {upcoming_trip_name} to {upcoming_trip_dest} starts in {upcoming_trip_days} days.")
        else:
            briefing_parts.append("You don't have any active or upcoming trips scheduled right now.")

        # Weather
        if weather_temp is not None:
            w_desc = weather_desc or "clear sky"
            briefing_parts.append(f"Weather at your location is {w_desc} with a temperature of {int(weather_temp)} degrees.")

        # Group update
        if group_name and group_expenses_count > 0:
            briefing_parts.append(f"Your group {group_name} has active updates, including {group_expenses_count} new expenses added today.")

        return " ".join(briefing_parts)

    async def generate_itinerary(self, data: dict) -> dict:
        """
        Generates a custom day-wise itinerary using free AI models.
        """
        destination = data.get("destination", "Unknown")
        days = int(data.get("days", 3))
        budget = data.get("budget", "")
        interests = data.get("interests", ["historical"])
        travel_style = data.get("travelStyle", "mid-range")
        group_solo = data.get("groupSoloMode", "solo")
        user_profile = data.get("userProfile", {})
        previous_trips = data.get("previousTrips", [])

        interests_str = ", ".join(interests)
        past_trips_context = ""
        if previous_trips:
            past_trips_context = "The user has previously visited: " + ", ".join([t.get("destination", "") for t in previous_trips if t.get("destination")]) + ". Avoid repeating exact elements, instead suggest new sights or build on their preferences."
        
        profile_context = ""
        if user_profile:
            p_pref = user_profile.get("preferences", "")
            p_style = user_profile.get("travelStyle", "")
            if p_pref or p_style:
                profile_context = f"User Profile Preferences: {p_pref}. Preferred style: {p_style}."

        prompt = f"""Generate a detailed, custom day-by-day travel itinerary for a {days}-day trip to {destination}.
Trip Parameters:
- Destination: {destination}
- Duration: {days} days
- Budget: {budget}
- Travel Style: {travel_style} (budget, comfort/mid-range, luxury)
- Interests: {interests_str}
- Group/Solo Mode: {group_solo}
{profile_context}
{past_trips_context}

The response MUST be a valid JSON object matching this schema exactly:
{{
  "destination": "{destination}",
  "totalDays": {days},
  "itinerary": [
    {{
      "day": 1,
      "title": "Day Title (e.g. Arrival & Beach Walk)",
      "morning": "Morning activity description with restaurant/cafe suggestions",
      "afternoon": "Afternoon activity description with attraction details",
      "evening": "Evening activity description with dinner spots and hidden gems",
      "notes": "Custom travel tip, local safety advice, transport recommendation, and budget notes."
    }}
  ]
}}

Ensure that activities contain specific local restaurants, actual sightseeing attractions, transport tips, and local hidden gems in {destination}. Each day must have a different theme and set of stops. Respond with ONLY the raw JSON string."""

        system_instruction = "You are a professional travel planner API that outputs only valid JSON strings. You never include conversational preamble, and your JSON is always clean, well-formed, and strictly parses."

        try:
            content = await ai_provider.generate_text(
                system_instruction=system_instruction,
                prompt=prompt,
                force_json=True
            )
            if content:
                cleaned = content.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
                
                import json
                parsed = json.loads(cleaned)
                if "itinerary" in parsed:
                    return parsed
        except Exception as e:
            logger.error("Free AI itinerary generation failed, falling back: %s", e)

        # Fallback to local template logic
        return self._generate_fallback_itinerary(destination, days, interests, travel_style, group_solo)

    async def get_safety_assessment(self, city: str) -> dict:
        """
        Determines safety score, weather hazard index, traffic delays, hidden gems
        by fetching live weather data and analyzing via free AI models.
        """
        lat, lon, country = 0.0, 0.0, ""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
                )
                if res.status_code == 200:
                    results = res.json().get("results", [])
                    if results:
                        lat = results[0]["latitude"]
                        lon = results[0]["longitude"]
                        country = results[0].get("country", "")
        except Exception as e:
            logger.warning("Geocoding failed for %s: %s", city, e)

        weather_info = "Weather data unavailable"
        temp = None
        if lat != 0.0 or lon != 0.0:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.get(
                        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                    )
                    if res.status_code == 200:
                        data = res.json()
                        current = data.get("current_weather", {})
                        temp = current.get("temperature")
                        wcode = current.get("weathercode", 0)
                        
                        w_descs = {
                            0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
                            45: "foggy", 48: "depositing rime fog", 51: "light drizzle",
                            53: "moderate drizzle", 55: "dense drizzle", 61: "slight rain",
                            63: "moderate rain", 65: "heavy rain", 71: "slight snow fall",
                            73: "moderate snow fall", 75: "heavy snow fall", 77: "snow grains",
                            80: "slight rain showers", 81: "moderate rain showers",
                            82: "violent rain showers", 85: "slight snow showers",
                            86: "heavy snow showers", 95: "thunderstorm", 96: "thunderstorm with slight hail",
                            99: "thunderstorm with heavy hail"
                        }
                        w_desc = w_descs.get(wcode, "cloudy")
                        weather_info = f"Current temperature: {temp}°C. Weather status: {w_desc}."
            except Exception as e:
                logger.warning("Weather fetch failed: %s", e)

        prompt = f"""Perform a travel safety, traffic, and local risk assessment for the city: {city}, {country}.
Current weather context: {weather_info}

Analyze safety score (general safety rating 0-10, night safety walking rating 0-10), traffic congestion transit delays, weather hazard index, 3 local hidden gems (non-touristy, unique spots with brief descriptions), and specific travel recommendations.

The response MUST be a valid JSON object matching this schema exactly:
{{
  "city": "{city}",
  "generalSafety": 8.5,
  "nightSafety": 8.0,
  "trafficIndex": "Moderate Traffic",
  "weatherHazard": "Low Risk",
  "gems": [
    {{
      "name": "Gem Name",
      "desc": "Short description of the gem"
    }}
  ],
  "recommendations": "Provide a detailed travel advisory alert and safety advice based on the location and current weather."
}}

Respond ONLY with the raw JSON string."""

        system_instruction = "You are a dynamic travel safety API that outputs only valid JSON strings. You assess safety scores, travel warnings, and hidden gems."

        try:
            content = await ai_provider.generate_text(
                system_instruction=system_instruction,
                prompt=prompt,
                force_json=True
            )
            if content:
                cleaned = content.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
                
                import json
                parsed = json.loads(cleaned)
                return parsed
        except Exception as e:
            logger.error("Free AI safety assessment failed: %s", e)

        # Fallback to local template-based logic
        return self._generate_fallback_safety(city, country, temp)

    async def generate_voice_response(self, query: str, context: dict) -> str:
        """
        Generates a warm, conversational spoken response to a user query
        using their active/upcoming trip, group activities, weather, and traffic data using free AI models.
        """
        user_name = context.get("userName", "Traveler")
        active_trip = context.get("activeTrip")
        upcoming_trip = context.get("upcomingTrip")
        groups = context.get("groups", [])

        active_trip_str = "None"
        if active_trip:
            active_trip_str = f"Trip Name: {active_trip.get('tripName')}, Destination: {active_trip.get('destination')}, Budget: {active_trip.get('budget')}, Dates: {active_trip.get('startDate')} to {active_trip.get('endDate')}"
            days = active_trip.get("days", [])
            if days:
                active_trip_str += f", Days planned: {len(days)}"
        
        upcoming_trip_str = "None"
        if upcoming_trip:
            upcoming_trip_str = f"Trip Name: {upcoming_trip.get('tripName')}, Destination: {upcoming_trip.get('destination')}, Budget: {upcoming_trip.get('budget')}, Starts: {upcoming_trip.get('startDate')}"

        groups_str = "None"
        if groups:
            groups_str = "; ".join([
                f"Group Name: {g.get('groupName', g.get('name', 'Unnamed'))}, Members Count: {len(g.get('memberUids', []))}, Expenses Count: {len(g.get('expenses', []))}"
                for g in groups
            ])

        prompt = f"""Answer the user's spoken travel query.
User: {user_name}
Query: "{query}"

Context:
- Active Trip: {active_trip_str}
- Upcoming Trip: {upcoming_trip_str}
- Group Trips Details: {groups_str}
- Current Local Time: 2026-06-10

Provide a natural, conversational response that directly answers the user's query using the context details above. 
Keep it concise (3-4 sentences maximum) and suitable for a text-to-speech engine (do not include markdown formatting, bullet points, asterisks, hash tags, or special characters). Speak directly and warmly to the user."""

        system_instruction = "You are a warm, helpful voice assistant for TripSync. You speak directly and naturally. Never use markdown or special symbols in your output, only plain readable text."

        try:
            content = await ai_provider.generate_text(
                system_instruction=system_instruction,
                prompt=prompt,
                force_json=False
            )
            if content:
                return content.strip().replace("*", "").replace("#", "")
        except Exception as e:
            logger.error("Free AI voice response failed: %s", e)

        # Fallback simple answer based on keywords
        return self._generate_fallback_voice(query, context)

    def _generate_fallback_itinerary(self, destination: str, days: int, interests: list, travel_style: str, group_solo: str) -> dict:
        templates = {
            "beach": [
                {"morning": "Sunrise Beach Yoga & Swim", "afternoon": "Water Sports & Jet Skiing", "evening": "Coastal Seafood Sunset BBQ"},
                {"morning": "Secret Beach Cove Trek", "afternoon": "Snorkeling & Kayaking Trip", "evening": "Beachside Cabin Dinner & Drums"},
            ],
            "nature": [
                {"morning": "Nature Forest Trail Walk", "afternoon": "Birdwatching & Lake Boating", "evening": "Scenic Mountain Viewpoint Sunset"},
                {"morning": "Hike to Hidden Forest Waterfall", "afternoon": "Wildlife Sanctuary Safari Ride", "evening": "Stargazing Campfire Gathering"},
            ],
            "historical": [
                {"morning": "Ancient Fort & Museum Guided Tour", "afternoon": "Old Heritage Street Walking Trail", "evening": "Cultural Light & Sound Show"},
                {"morning": "Archaeological Sites Exploration", "afternoon": "Local Historical Archives & Arts Gallery", "evening": "Traditional Heritage Dinner"},
            ],
            "adventure": [
                {"morning": "Early Mountain Peak Trekking Ascent", "afternoon": "River Rafting & Rock Climbing", "evening": "Alpine Campfire & BBQ"},
                {"morning": "Forest ATV Trail Riding Tour", "afternoon": "Zip-Lining & Bungee Adventure", "evening": "Hilltop Camp stargazing"},
            ],
            "food": [
                {"morning": "Local Food Market & Tasting Tour", "afternoon": "Culinary Class with Local Chef", "evening": "Fine Dining Regional Cuisine Experience"},
                {"morning": "Organic Spice Plantation Walk", "afternoon": "Traditional Bakery & Street Cafe Tour", "evening": "Rooftop Craft Brews & Street Food"},
            ],
            "luxury": [
                {"morning": "Private Yacht Sailing & Sunbathing", "afternoon": "Exclusive Helicopter City Scenic Flight", "evening": "Rooftop Fine Dining Tasting Menu"},
                {"morning": "Premium Full Body Spa & Treatment", "afternoon": "High-End Golf Club Session", "evening": "VIP Beach Club Reserved Lounge"},
            ],
            "shopping": [
                {"morning": "Artisan Flea Market Bargain Hunting", "afternoon": "Shopping Mall Designer Brands Tour", "evening": "Night Bazaar Souvenirs Shopping"},
                {"morning": "Local Weaving & Handicraft Center", "afternoon": "Boutique Alleyways Crafts Tour", "evening": "Spice and Tea Bazaar Walk"},
            ],
            "nightlife": [
                {"morning": "Late Morning Cafe Relaxation", "afternoon": "Scenic City Panoramic Tour", "evening": "Trendy Pub Crawl & Live Music Lounge"},
                {"morning": "Art Gallery & Historic Buildings Walk", "afternoon": "Twilight Riverside Walk", "evening": "Club Night DJ Dance Party"},
            ],
            "wellness": [
                {"morning": "Guided Sunrise Yoga & Meditation", "afternoon": "Natural Hot Springs Spa Relaxation", "evening": "Healthy Organic Farm-to-Table Dinner"},
                {"morning": "Silent Walking Forest Meditation", "afternoon": "Ayurvedic Treatment & Massage", "evening": "Sunset Reflection Zen Garden Tour"},
            ],
        }

        itinerary = []
        valid_interests = [i for i in interests if i in templates]
        if not valid_interests:
            valid_interests = ["historical"]

        for d in range(1, days + 1):
            day_interest = valid_interests[(d - 1) % len(valid_interests)]
            pool = templates[day_interest]
            act_template = pool[(d - 1) % len(pool)]

            style_notes = ""
            if travel_style == "budget":
                style_notes = "💡 Style Alert: Budget! Use local shared transit, walk when possible, and opt for local street food vendors."
            elif travel_style == "luxury":
                style_notes = "💎 Style Alert: Premium! Private chauffeur booking recommended, VIP reservations arranged, fine dining reserved."
            else:
                style_notes = "🚗 Style Alert: Comfort! Standard rideshares, balanced cafe dining, pre-book major landmarks."

            setup_notes = ""
            if group_solo == "group":
                setup_notes = "👥 Group Setup: Share navigation details and splits in the Groups section! Coordinate meeting at the morning spot."
            else:
                setup_notes = "🎒 Solo Setup: Take safe routes, keep emergency contacts on quick-dial, and stay alert during late hours."

            itinerary.append({
                "day": d,
                "title": f"Day {d} – {day_interest.capitalize()} in {destination}",
                "morning": act_template["morning"],
                "afternoon": act_template["afternoon"],
                "evening": act_template["evening"],
                "notes": f"Enjoy day {d} of your custom trip to {destination}! \n{style_notes} \n{setup_notes}"
            })

        return {
            "destination": destination,
            "totalDays": days,
            "itinerary": itinerary
        }

    def _generate_fallback_safety(self, city: str, country: str = "", temp: float = None) -> dict:
        city_data = {
            "goa":       {"generalSafety": 8.7, "nightSafety": 7.9, "trafficIndex": "Moderate Traffic", "weatherHazard": "Low Risk"},
            "delhi":     {"generalSafety": 7.2, "nightSafety": 6.5, "trafficIndex": "Heavy Transit",    "weatherHazard": "High (Air Quality)"},
            "mumbai":    {"generalSafety": 8.1, "nightSafety": 7.8, "trafficIndex": "Heavy Transit",    "weatherHazard": "Moderate (Monsoon)"},
            "bangalore": {"generalSafety": 8.4, "nightSafety": 8.1, "trafficIndex": "Moderate Traffic", "weatherHazard": "Low Risk"},
            "manali":    {"generalSafety": 8.9, "nightSafety": 8.3, "trafficIndex": "Mild Delays",      "weatherHazard": "Moderate (Snow)"},
            "jaipur":    {"generalSafety": 8.0, "nightSafety": 7.3, "trafficIndex": "Moderate Traffic", "weatherHazard": "Low Risk"},
            "kerala":    {"generalSafety": 9.1, "nightSafety": 8.7, "trafficIndex": "Mild Delays",      "weatherHazard": "Moderate (Monsoon)"},
            "ladakh":    {"generalSafety": 9.3, "nightSafety": 9.0, "trafficIndex": "Mild Delays",      "weatherHazard": "High (Altitude)"},
        }

        key = city.lower().strip()
        data = city_data.get(key)

        if not data:
            hash_val = len(city) % 3
            data = {
                "generalSafety": round(8.2 + hash_val * 0.4, 1),
                "nightSafety":   round(7.8 + hash_val * 0.3, 1),
                "trafficIndex":  ["Mild Delays", "Moderate Traffic", "Heavy Transit"][hash_val],
                "weatherHazard": "Low Risk" if hash_val < 2 else "Moderate (Variable)",
            }

        weather_notes = ""
        if temp is not None:
            weather_notes = f" Temperature is around {temp}°C."

        return {
            "city": city.title(),
            **data,
            "gems": [
                {"name": f"{city.title()} Sunrise Vista",        "desc": "A quiet viewpoint with breathtaking early morning light – away from tourist crowds"},
                {"name": "Heritage Lane Market",                  "desc": "Vibrant local bazaar with authentic handicrafts and regional street food"},
                {"name": f"{city.title()} Lakeside Café",         "desc": "Cozy waterfront café with local brews and stunning nature views"},
            ],
            "recommendations": f"Travel to {city.title()} is generally safe. Maintain standard vigilance.{weather_notes}"
        }

    def _generate_fallback_voice(self, query: str, context: dict) -> str:
        q = query.lower()
        user_name = context.get("userName", "Traveler")
        active_trip = context.get("activeTrip")
        upcoming_trip = context.get("upcomingTrip")
        groups = context.get("groups", [])

        if "trip" in q or "next" in q or "schedule" in q:
            if active_trip:
                return f"Hello {user_name}. You are currently on your active trip {active_trip.get('tripName')} in {active_trip.get('destination')}. Your schedule is fully planned."
            elif upcoming_trip:
                return f"Hello {user_name}. Your next trip is {upcoming_trip.get('tripName')} to {upcoming_trip.get('destination')} starting on {upcoming_trip.get('startDate')}."
            else:
                return f"Hello {user_name}. You do not have any active or upcoming trips scheduled right now."
        
        if "budget" in q or "expense" in q or "cost" in q:
            if active_trip:
                return f"The budget for your active trip to {active_trip.get('destination')} is {active_trip.get('budget')} rupees. Remember to track expenses in your groups."
            else:
                return f"You don't have an active trip budget right now. Use the AI Trip Planner to schedule a trip with a budget."

        if "group" in q or "update" in q or "member" in q:
            if groups:
                main_group = groups[0]
                g_name = main_group.get("groupName", main_group.get("name", "Unnamed"))
                m_count = len(main_group.get("memberUids", []))
                return f"In your active group {g_name} with {m_count} members, everything is currently synchronized. Check the Groups tab for specific settles."
            else:
                return "You are not currently in any active travel groups."

        return f"Hello {user_name}. I can help you with travel schedules, budgets, safety, and group updates. Just ask me details."

    def _generate_sophisticated_fallback(self, message: str) -> str:
        msg = message.lower().strip()

        # Categories
        is_beach = any(k in msg for k in ["goa", "beach", "coastal", "sea", "ocean", "pondicherry", "kayak"])
        is_mountain = any(k in msg for k in ["manali", "himachal", "snow", "mountain", "himalayas", "ooty", "coorg", "trek", "hill"])
        is_history = any(k in msg for k in ["palace", "fort", "jaipur", "rajasthan", "heritage", "museum", "history", "ancient"])
        is_budget = any(k in msg for k in ["budget", "cheap", "cost", "expense", "money", "split", "rupee", "price", "fare"])
        is_safety = any(k in msg for k in ["safety", "safe", "solo", "woman", "night", "security", "emergency"])
        is_route = any(k in msg for k in ["route", "directions", "map", "tsp", "optimize", "stop", "tsp solver"])
        is_weather = any(k in msg for k in ["weather", "rain", "forecast", "temp", "temperature", "climate", "sun"])
        is_group = any(k in msg for k in ["group", "member", "split", "expense", "team", "traveler"])

        # Dynamic template data
        cities = ["Goa", "Manali", "Jaipur", "Coorg", "Ooty", "Pondicherry", "Mumbai", "Delhi"]
        selected_city = next((c for c in cities if c.lower() in msg), None)

        if is_beach:
            city = selected_city or "Goa"
            return f"""🏖️ **TripSync AI — {city} Coastal Travel Guide**

Here is a curated itinerary and safety advisory for your coastal trip to **{city}**:

### 🌟 Top Recommendations & Hidden Gems
1. **Scenic Coastal Cliffs**: Best visited before 7:30 AM to avoid crowds and catch the perfect sunrise.
2. **Hidden Cove Beaches**: Secluded spots perfect for kayaking, stand-up paddleboarding, and photography.
3. **Local Shacks & Seafood**: Authentic coastal cuisine away from commercial tourist strips.

### 🛡️ Safety & Travel Tips
* **Tide Safety**: Check local tide tables before visiting tide pools.
* **Solo Travel**: Extremely safe, but avoid unlit beach lanes after 10 PM.
* **Transit Info**: Renting a local scooter (approx. ₹300-₹400/day) is highly recommended.

*Need help optimizing a multi-stop route or splitting budget expenses for this trip? Just ask!*"""

        elif is_mountain:
            city = selected_city or "Manali"
            return f"""🏔️ **TripSync AI — {city} Mountain Adventure Planner**

Here is a custom recommendation for your mountain getaway to **{city}**:

### 🥾 Recommended Activities
* **Sunrise Ridge Trek**: A scenic trail leading to panoramic valley views.
* **Riverside Cafés**: Cozy spots offering wood-fired pizzas and locally sourced organic herbal teas.
* **Adventure Sports**: Paragliding and river rafting options are available. Ensure operators are government-licensed.

### ❄️ Weather & Pack Guide
* **Current Weather**: Pleasant during daytime but temperature drops sharply post-sunset. 
* **Essentials**: Carry windcheaters, layered warm clothing, thermal wear, and sturdy hiking boots.

*You can use the Map tab to build a sequential multi-stop route for this adventure!*"""

        elif is_history:
            city = selected_city or "Jaipur"
            return f"""🏰 **TripSync AI — {city} Heritage & Culture Guide**

Explore the rich history and architecture of **{city}**:

### 🏛️ Must-Visit Spots
1. **The Royal Forts**: Excellent panoramic views. Hire registered guides at the entrance to learn the rich folklore.
2. **Heritage Market Alleys**: Famous for traditional handicrafts, block-print textiles, and regional street food.
3. **Local Art Museums**: Deep dive into historic weaponry, textiles, and paintings.

### 💡 Traveler Tip
* Visit major monuments between 8:00 AM and 10:30 AM to beat both heat and tourist bus rushes.
* Coordinate with your group using the Groups tab to track meeting points!"""

        elif is_budget:
            return """💰 **TripSync AI — Smart Travel Budget Advisory**

Here are practical, start-up-level budget planning strategies to maximize your savings:

### 🎒 Budget Hacks
* **Accommodations**: Opt for boutique hostels or homestays (average ₹400-₹800/night).
* **Local Commutes**: Use metro systems, local public buses, or shared autorickshaws instead of private taxis.
* **Dining**: Explore local dhabas and popular street food stalls for high-quality, authentic regional meals at fraction costs.
* **Expense Sync**: Create a Group inside the Groups tab to dynamically log and auto-split travel costs (cabs, food bills) with your friends.

*Tell me your destination and I can calculate a custom daily cost breakdown estimate!*"""

        elif is_safety:
            city = selected_city or "your destination"
            return f"""🛡️ **TripSync AI — Safety & Security Guide**

Your safety is our top priority. Here are safety metrics and guidelines for **{city}**:

### 📊 Safety Overview
* **General Safety**: 8.5/10 (Highly secure for tourists)
* **Night Walking**: 7.8/10 (Safe, stick to well-lit commercial streets)
* **Traffic Index**: Moderate (Be cautious crossing main junctions)

### 🚨 Actionable Checklist
1. **Live Location**: Always share your live location or active route with a trusted friend.
2. **Transportation**: Prefer booking rides via major ride-hailing apps (Uber, Ola) over street hailing at night.
3. **Emergency Numbers**: 
   * Police Support: `100`
   * Medical Emergency: `108`
   * TripSync Support: Available in-app"""

        elif is_route:
            return """📍 **TripSync AI — Route Optimization & Navigation**

Our Map Builder uses a **FastAPI TSP (Traveling Salesperson Problem) Solver** to optimize your journey:

### 🚀 How to build optimized routes:
1. Go to the **Map** tab and switch to **Builder** mode.
2. Search and add all your stops (e.g. Marina Beach, Mahabalipuram, Pondicherry).
3. Hit **Optimize**—our backend will reorder stops to create the absolute shortest driving path.
4. Press **Start** to trigger sequential, Google Maps-style navigation. It will guide you stop-by-stop, advancing only when you reach each stop!"""

        elif is_weather:
            city = selected_city or "your destination"
            return f"""☀️ **TripSync AI — Weather & Climate Advisory**

Here is the current forecast and packing recommendation for **{city}**:

### 🌦️ Climate Brief
* **Daytime**: Warm, sunny spells. Perfect for sightseeing and beach visits.
* **Nighttime**: Breezy, mild drops in temperature.
* **Recommendation**: Carry light cotton clothes, sunscreen (SPF 50+), sunglasses, and a compact umbrella just in case.

*To check live GPS-based weather at any coordinate, open the Maps explore categories!*"""

        elif is_group:
            return """👥 **TripSync AI — Group Travel Assistance**

Planning a trip with friends? Here is how to keep everything synced:

### 🔄 Real-time Features
* **Shared Itinerary**: Everyone in the group can view the day-by-day stops.
* **Expense Splits**: Log expenses inside the group details, and our backend will calculate who owes whom in real-time.
* **Sequential Navigation**: Shared route navigation means everyone arrives at the same stops together.

*Go to the Groups tab to create your group and invite friends!*"""

        # General helper response
        return f"""🤖 **Hello! I am your TripSync AI Travel Companion.**

I can assist you with all aspects of travel planning. Try asking me about:
* 🏖️ **Goa Beaches** or **Manali Cozy Cafes**
* 💰 **Budget advice** and cost-saving tips
* 🛡️ **Safety scores** for specific cities
* 📍 **Route optimization** and multi-stop builder navigation
* 🌦️ **Live weather advisories** and packing checklists

*What destination are you exploring next?*"""

# Single instance importable service
ai_service = AIService()
