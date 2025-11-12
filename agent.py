#!/usr/bin/env python3
"""
OpenTable Reservation Agent with ASI1 Integration
Includes async OTP handling and CDP-based credit card iframe filling
"""

import os
import asyncio
import json
import random
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Optional
from uuid import uuid4
from dotenv import load_dotenv
from openai import AsyncOpenAI

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

from browser_use import Agent as BrowserAgent, Tools, ChatGoogle, ActionResult
from browser_use.browser.session import BrowserSession
from pydantic import BaseModel

# Load environment
load_dotenv()

# Disable Chrome security for cross-origin iframes
os.environ['PLAYWRIGHT_CHROMIUM_ARGS'] = '--disable-web-security --disable-features=IsolateOrigins,site-per-process --disable-site-isolation-trials'

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Credit card details for testing
CARD_DATA = {
    'name on the card': 'Rajashekar Vennavelli',
    'number': '4676214000389100',
    'expiry_month': '03',
    'expiry_year': '27',
    'cvv': '317',
    'zip': '94704'
}

# Create the uAgent
agent = Agent(
    name="opentable_reservation_agent",
    seed="opentable_seed_phrase_123",
    port=8001,
    mailbox=True
)

# Initialize chat protocol
chat_proto = Protocol(spec=chat_protocol_spec)

# Global OTP queues
OTP_QUEUES = {}

# Session state storage
SESSION_STATE = {}

# Empty Pydantic model for tools with no parameters
class EmptyParams(BaseModel):
    """No parameters needed for this tool"""
    pass


# Pydantic model for OpenTable date/time/party selector tool
class OpenTableSelectorParams(BaseModel):
    """Parameters for selecting date, time, and party size on OpenTable homepage"""
    date: str  # Format: YYYY-MM-DD (e.g., "2025-11-04")
    time: str  # Format: "7:30 PM"
    party_size: int  # Number 1-21


def create_text_chat(text: str) -> ChatMessage:
    """Helper to create a text chat message"""
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(text=text)]
    )


def resolve_date(date_str: str, location: str = None) -> str:
    """Convert relative dates like 'today' or 'tomorrow' to actual dates
    
    Uses proper IANA timezone database to handle DST automatically.
    Dates are resolved based on the restaurant's local timezone.
    """
    if not date_str:
        return 'today'
    
    date_str_lower = date_str.lower().strip()
    
    # Map locations to IANA timezone identifiers
    # These handle DST automatically!
    timezone_map = {
        # US West Coast
        'san francisco': 'America/Los_Angeles',
        'sf': 'America/Los_Angeles',
        'california': 'America/Los_Angeles',
        'ca': 'America/Los_Angeles',
        'bay area': 'America/Los_Angeles',
        'los angeles': 'America/Los_Angeles',
        'la': 'America/Los_Angeles',
        'seattle': 'America/Los_Angeles',
        'portland': 'America/Los_Angeles',
        'san diego': 'America/Los_Angeles',
        
        # US East Coast
        'new york': 'America/New_York',
        'ny': 'America/New_York',
        'nyc': 'America/New_York',
        'manhattan': 'America/New_York',
        'boston': 'America/New_York',
        'washington': 'America/New_York',
        'philadelphia': 'America/New_York',
        'miami': 'America/New_York',
        'atlanta': 'America/New_York',
        
        # US Central
        'chicago': 'America/Chicago',
        'dallas': 'America/Chicago',
        'houston': 'America/Chicago',
        
        # US Mountain
        'denver': 'America/Denver',
        'phoenix': 'America/Phoenix',  # No DST in Arizona
        
        # International
        'london': 'Europe/London',
        'uk': 'Europe/London',
        'england': 'Europe/London',
        'paris': 'Europe/Paris',
        'france': 'Europe/Paris',
        'tokyo': 'Asia/Tokyo',
        'japan': 'Asia/Tokyo',
        'sydney': 'Australia/Sydney',
        'australia': 'Australia/Sydney',
        'dubai': 'Asia/Dubai',
    }
    
    # Determine the appropriate timezone
    tz = None
    if location:
        location_lower = location.lower()
        for city, tz_name in timezone_map.items():
            if city in location_lower:
                try:
                    tz = ZoneInfo(tz_name)
                    break
                except Exception:
                    # If timezone not available, continue searching
                    continue
    
    # Default to US Pacific if no match (most US OpenTable restaurants)
    if tz is None:
        try:
            tz = ZoneInfo('America/Los_Angeles')
        except Exception:
            # Fallback to UTC if ZoneInfo not available
            tz = timezone.utc
    
    # Get current time in the target timezone
    now = datetime.now(tz)
    
    # Resolve relative dates
    if date_str_lower == 'today':
        return now.strftime('%Y-%m-%d')
    elif date_str_lower == 'tomorrow':
        return (now + timedelta(days=1)).strftime('%Y-%m-%d')
    elif 'day after tomorrow' in date_str_lower:
        return (now + timedelta(days=2)).strftime('%Y-%m-%d')
    else:
        # Return as-is if it's already a specific date or day name
        return date_str


async def extract_info_with_openai(ctx: Context, user_message: str) -> Dict:
    """Use OpenAI to extract reservation details and user info from natural language"""
    
    if not openai_client:
        return {'status': 'no_openai', 'data': {}}
    
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": """Extract reservation and user information from the message. Return JSON with:
{
  "intent": "book" | "provide_info" | "unclear",
  "restaurant": "name" or null,
  "location": "city" or null,
  "first_name": "name" or null,
  "last_name": "name" or null,
  "email": "email@domain.com" or null,
  "phone": "phone number" or null,
  "date": "today|tomorrow|specific date" or null,
  "time": "7:30 PM" or null,
  "party_size": number or null
}

Examples:
"Book Amber India tomorrow at 8pm for 4 people, John Doe (john@email.com, 415-555-1234)" -> {"intent": "book", "restaurant": "Amber India", "first_name": "John", "last_name": "Doe", "email": "john@email.com", "phone": "415-555-1234", "date": "tomorrow", "time": "8pm", "party_size": 4}
"Reserve Che Fico today for 2, Sarah Smith sarah@gmail.com 650-555-9876" -> {"intent": "book", "restaurant": "Che Fico", "first_name": "Sarah", "last_name": "Smith", "email": "sarah@gmail.com", "phone": "650-555-9876", "date": "today", "party_size": 2}
"My name is Mike Jones, phone +44 7911 123456" -> {"intent": "provide_info", "first_name": "Mike", "last_name": "Jones", "phone": "+44 7911 123456"}
"""
            }, {
                "role": "user",
                "content": user_message
            }],
            temperature=0
        )
        
        content = response.choices[0].message.content.strip()
        
        # Parse JSON
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        
        result = json.loads(content)
        ctx.logger.info(f"OpenAI extraction: {result}")
        return {'status': 'success', 'data': result}
        
    except Exception as e:
        ctx.logger.error(f"OpenAI extraction failed: {e}")
        return {'status': 'error', 'data': {}}


async def run_reservation_task(ctx: Context, sender: str, restaurant: str, location: str, first_name: str, last_name: str, email: str, phone: str, date: str, time: str, party_size: int):
    """Wrapper task that runs reservation and sends final result"""
    result = await run_reservation(ctx, sender, restaurant, location, first_name, last_name, email, phone, date, time, party_size)
    
    # Send final result to user
    if result['success']:
        success_msg = f"""Reservation Confirmed!

Restaurant: {restaurant} in {location}
Confirmation sent to: {email}

Enjoy your meal!"""
        await ctx.send(sender, create_text_chat(success_msg))
    else:
        error_msg = f"""Reservation Failed

{result['message']}"""
        await ctx.send(sender, create_text_chat(error_msg))


async def run_reservation(ctx: Context, sender: str, restaurant: str, location: str, first_name: str, last_name: str, email: str, phone: str, date: str, time: str, party_size: int):
    """Run browser automation with async OTP handling and CDP-based credit card filling"""
    
    # Create OTP queue for this session
    otp_queue = asyncio.Queue()
    OTP_QUEUES[sender] = otp_queue
    ctx.logger.info(f"Created OTP queue for {sender}")
    
    # Initialize tools
    tools = Tools()
    
    @tools.action(description='Ask human to provide the OTP/verification code when the reservation page asks for it. Use this when you see an OTP input field or verification code prompt.')
    async def get_otp_from_human(question: str = "Please enter the OTP/verification code") -> str:
        """Get OTP code from human via ASI1 chat - BLOCKS until OTP arrives"""
        ctx.logger.info("Agent requesting OTP")
        
        # Send message to user via ASI1
        otp_request_msg = f"""OTP Verification Required

A verification code has been sent to your email or phone.

Please send me the OTP code to complete your reservation for:
- Restaurant: {restaurant}
- Location: {location}

Just reply with the code (e.g., "123456")"""
        
        await ctx.send(sender, create_text_chat(otp_request_msg))
        
        # Block here waiting for OTP from chat handler
        ctx.logger.info("Waiting for OTP from user...")
        otp_code = await otp_queue.get()
        ctx.logger.info(f"Got OTP: {otp_code}")
        
        return otp_code
    
    @tools.registry.action('Fill credit card iframe fields using CDP', param_model=EmptyParams)
    async def fill_credit_card_form(browser_session: BrowserSession):
        """Fill ONLY the Spreedly iframe fields (card number + CVV) using CDP.
        
        This tool fills cross-origin iframe fields that the agent cannot access directly.
        After calling this tool, you MUST manually fill the remaining main page fields:
        - Name on Card
        - Expiry Date (MM/YY format)
        - ZIP Code
        
        Call this tool WITHOUT parameters when you see the credit card form.
        """
        
        ctx.logger.info("="*60)
        ctx.logger.info("CREDIT CARD TOOL ACTIVATED - CDP Direct Access")
        ctx.logger.info("="*60)
        
        try:
            # Get current page
            page = await browser_session.must_get_current_page()
            current_url = await page.get_url()
            ctx.logger.info(f"Current URL: {current_url}")
            
            # Get all frames
            ctx.logger.info("Discovering all frames...")
            all_frames, target_sessions = await browser_session.get_all_frames()
            
            ctx.logger.info(f"Found {len(all_frames)} total frames")
            
            # Find payment iframes
            payment_frames = []
            
            ctx.logger.info(f"Searching for payment iframes in {len(all_frames)} frames...")
            for frame_id, frame_info in all_frames.items():
                if isinstance(frame_info, dict):
                    frame_url = frame_info.get('url', '').lower()
                    ctx.logger.info(f"Checking frame: {frame_url[:80]}...")
                    
                    # Check for payment processor domains
                    if any(keyword in frame_url for keyword in ['spreedly', 'payment', 'stripe', 'square']):
                        ctx.logger.info(f"FOUND payment iframe: {frame_url}")
                        payment_frames.append({
                            'id': frame_id,
                            'url': frame_info.get('url'),
                            'cross_origin': True
                        })
            
            if not payment_frames:
                return ActionResult(
                    is_done=False,
                    extracted_content='Could not find payment iframes (Spreedly/Stripe/Square)'
                )
            
            ctx.logger.info(f"Found {len(payment_frames)} payment iframe(s)")
            for idx, frame in enumerate(payment_frames):
                ctx.logger.info(f"[{idx}] {frame['url']}")
            
            # Prepare card data
            card_data_map = {
                'card_number': CARD_DATA['number'].replace(' ', ''),
                'month': CARD_DATA['expiry_month'],
                'year': CARD_DATA['expiry_year'][-2:],
                'cvv': CARD_DATA['cvv'],
                'full_name': CARD_DATA['name on the card'],
                'zip': CARD_DATA['zip']
            }
            
            filled_count = 0
            ctx.logger.info("Inspecting and filling each iframe...")
            
            # Process each iframe
            for frame_idx, frame_info in enumerate(payment_frames):
                frame_id = frame_info['id']
                frame_url = frame_info['url']
                
                try:
                    # Get CDP client for this iframe
                    cdp_client = await browser_session.cdp_client_for_frame(frame_id)
                    if not cdp_client:
                        ctx.logger.warning(f"Frame [{frame_idx}]: Could not get CDP client")
                        continue
                    
                    # Inspect what field is in this iframe
                    inspect_js = """
                    (function() {
                        const input = document.querySelector('input');
                        if (!input) return {found: false};
                        return {
                            found: true,
                            name: input.name || '',
                            id: input.id || '',
                            type: input.type || 'text',
                            placeholder: input.placeholder || '',
                            hasValue: !!(input.value && input.value.length > 0)
                        };
                    })()
                    """
                    
                    try:
                        inspect_result = await cdp_client.cdp_client.send.Runtime.evaluate(
                            params={
                                'expression': inspect_js,
                                'returnByValue': True,
                                'awaitPromise': False
                            },
                            session_id=cdp_client.session_id
                        )
                        field_info = inspect_result.get('result', {}).get('value', {})
                    except Exception as cdp_err:
                        ctx.logger.warning(f"Frame [{frame_idx}]: CDP inspect failed - {cdp_err}")
                        continue
                    
                    if not field_info.get('found'):
                        ctx.logger.warning(f"Frame [{frame_idx}]: No input found")
                        continue
                    
                    field_name = field_info.get('name', '')
                    field_id = field_info.get('id', '')
                    already_filled = field_info.get('hasValue', False)
                    
                    ctx.logger.info(f"Frame [{frame_idx}]: Found field name='{field_name}' id='{field_id}' (hasValue={already_filled})")
                    
                    # Determine what value to fill based on field name/id
                    value_to_fill = None
                    field_label = None
                    
                    if 'card_number' in field_name or 'card_number' in field_id or 'number' in field_name:
                        value_to_fill = card_data_map['card_number']
                        field_label = "Card Number"
                    elif 'month' in field_name or 'month' in field_id:
                        value_to_fill = card_data_map['month']
                        field_label = "Expiry Month"
                    elif 'year' in field_name or 'year' in field_id:
                        value_to_fill = card_data_map['year']
                        field_label = "Expiry Year"
                    elif 'cvv' in field_name or 'cvv' in field_id or 'cvc' in field_name:
                        value_to_fill = card_data_map['cvv']
                        field_label = "CVV"
                    elif 'full_name' in field_name or 'name' in field_name:
                        value_to_fill = card_data_map['full_name']
                        field_label = "Name on Card"
                    elif 'zip' in field_name or 'postal' in field_name:
                        value_to_fill = card_data_map['zip']
                        field_label = "ZIP Code"
                    else:
                        ctx.logger.warning(f"Unknown field type, skipping")
                        continue
                    
                    # Fill the field
                    fill_js = f"""
                    (function() {{
                        const input = document.querySelector('input');
                        if (!input) return {{success: false}};
                        
                        input.focus();
                        input.value = '{value_to_fill}';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.blur();
                        
                        return {{success: true}};
                    }})()
                    """
                    
                    try:
                        fill_result = await cdp_client.cdp_client.send.Runtime.evaluate(
                            params={
                                'expression': fill_js,
                                'returnByValue': True,
                                'awaitPromise': False
                            },
                            session_id=cdp_client.session_id
                        )
                        
                        if fill_result.get('result', {}).get('value', {}).get('success'):
                            ctx.logger.info(f"{field_label} filled successfully!")
                            filled_count += 1
                            await asyncio.sleep(random.uniform(0.3, 0.6))
                        else:
                            ctx.logger.warning(f"Failed to fill {field_label}")
                    except Exception as cdp_err:
                        ctx.logger.warning(f"CDP fill error for {field_label}: {cdp_err}")
                        
                except Exception as e:
                    ctx.logger.warning(f"Frame [{frame_idx}]: Error - {str(e)}")
                    continue
            
            ctx.logger.info(f"Successfully filled {filled_count} iframe field(s)!")
            ctx.logger.info("="*60)
            
            # OpenTable uses only 2 Spreedly iframes (number + CVV)
            # Other fields (name, expiry, zip) are on main page
            if filled_count >= 2:
                return ActionResult(
                    is_done=False,
                    extracted_content=f'IFRAME FIELDS COMPLETE! Filled card number ending in {CARD_DATA["number"][-4:]} and CVV in secure iframes. DO NOT call this tool again. Now immediately fill the 3 remaining main page fields: Name on Card = "{CARD_DATA["name on the card"]}", Expiry Date = "{CARD_DATA["expiry_month"]}/{CARD_DATA["expiry_year"][-2:]}", ZIP Code = "{CARD_DATA["zip"]}". Then accept terms and click Complete Reservation.'
                )
            elif filled_count > 0:
                return ActionResult(
                    is_done=False,
                    extracted_content=f'Partially filled: {filled_count} iframe field(s). Continue filling remaining fields.'
                )
            else:
                return ActionResult(
                    is_done=False,
                    extracted_content='Could not fill iframe credit card fields. Continue with main page fields: Name on Card, Expiry, ZIP.'
                )
                
        except Exception as e:
            ctx.logger.error(f"Error in credit card tool: {str(e)}")
            import traceback
            traceback.print_exc()
            return ActionResult(
                is_done=False,
                extracted_content=f'Tool error: {str(e)}'
            )
    
    @tools.registry.action('Select date, time, and party size on OpenTable homepage', param_model=OpenTableSelectorParams)
    async def select_opentable_date_time_party(params: OpenTableSelectorParams, browser_session: BrowserSession):
        """Reliably select date, time, and party size on OpenTable.com homepage using REAL selectors.
        
        This tool uses the ACTUAL OpenTable DOM selectors discovered via browser inspection.
        Call this tool BEFORE searching for the restaurant.
        
        Args:
            date: Date in YYYY-MM-DD format (e.g., "2025-11-04")
            time: Time like "7:30 PM" (must match OpenTable's format exactly)
            party_size: Number of people (1-21)
        """
        try:
            # Get current page
            page = await browser_session.must_get_current_page()
            
            ctx.logger.info(f"🎯 OpenTable Selector Tool - Date: {params.date}, Time: {params.time}, Party: {params.party_size}")
            
            # Parse date for calendar selection
            date_obj = datetime.strptime(params.date, '%Y-%m-%d')
            target_day = str(date_obj.day)
            target_month = date_obj.strftime('%B')  # Full month name
            
            # STEP 1: Date Selection (Calendar picker)
            ctx.logger.info("--- STEP 1: Date Selection ---")
            
            # Click date picker button
            date_click_js = f"""
            () => {{
                const dateBtn = document.querySelector('[data-test="day-picker"], [aria-label*="Date"]');
                if (dateBtn) {{
                    dateBtn.click();
                    return 'Clicked date picker';
                }}
                return 'Date picker not found';
            }}
            """
            
            result = await page.evaluate(date_click_js)
            ctx.logger.info(f"📅 {result}")
            await asyncio.sleep(0.8)
            
            # Click specific day
            day_click_js = f"""
            () => {{
                const dayBtn = Array.from(document.querySelectorAll('button[name="day"]'))
                    .find(btn => btn.textContent.trim() === '{target_day}' && 
                                 btn.getAttribute('aria-label').includes('{target_month}'));
                if (dayBtn) {{
                    dayBtn.click();
                    return 'Clicked day {target_day}';
                }}
                return 'Day {target_day} not found';
            }}
            """
            
            result = await page.evaluate(day_click_js)
            ctx.logger.info(f"✅ {result}")
            await asyncio.sleep(0.5)
            
            # STEP 2: Time Selection (select element with id="time-picker")
            ctx.logger.info("--- STEP 2: Time Selection ---")
            
            time_select_js = f"""
            () => {{
                const timeSelect = document.querySelector('#time-picker, select[data-test="time-picker"]');
                if (!timeSelect) return 'Time selector not found';
                
                // Find option by text content (e.g., "7:30 PM")
                const options = Array.from(timeSelect.options);
                const targetOption = options.find(opt => opt.textContent.trim() === '{params.time}');
                
                if (targetOption) {{
                    timeSelect.value = targetOption.value;
                    timeSelect.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return 'Selected time {params.time}';
                }}
                
                return 'Time {params.time} not found in options';
            }}
            """
            
            result = await page.evaluate(time_select_js)
            ctx.logger.info(f"✅ {result}")
            await asyncio.sleep(0.3)
            
            # STEP 3: Party Size Selection (select element with id="party-size-picker")
            ctx.logger.info("--- STEP 3: Party Size Selection ---")
            
            party_select_js = f"""
            () => {{
                const partySelect = document.querySelector('#party-size-picker, select[data-test="party-size-picker"]');
                if (!partySelect) return 'Party size selector not found';
                
                // Set value directly (1-21)
                partySelect.value = '{params.party_size}';
                partySelect.dispatchEvent(new Event('change', {{ bubbles: true }}));
                
                return 'Selected party size {params.party_size}';
            }}
            """
            
            result = await page.evaluate(party_select_js)
            ctx.logger.info(f"✅ {result}")
            await asyncio.sleep(0.3)
            
            success_msg = f"""✅ OpenTable Selector Tool Complete!

Selected:
- Date: {params.date} ({target_month} {target_day})
- Time: {params.time}
- Party Size: {params.party_size} people

The homepage selectors have been set. Now proceed to search for the restaurant."""

            ctx.logger.info(success_msg)
            
            return ActionResult(
                is_done=False,
                extracted_content=success_msg
            )
            
        except Exception as e:
            error_msg = f"❌ OpenTable Selector Tool Error: {str(e)}"
            ctx.logger.error(error_msg)
            return ActionResult(
                is_done=False,
                extracted_content=error_msg
            )
    
    @tools.registry.action('Verify page navigation to reservation form', param_model=EmptyParams)
    async def verify_reservation_page_loaded(browser_session: BrowserSession):
        """Verify that page successfully navigated to reservation details form after clicking time slot.
        
        This tool checks:
        - URL changed to reservation/booking page
        - Restaurant search bar is no longer visible
        
        Call this AFTER clicking a time slot to confirm the page navigation succeeded.
        """
        try:
            page = await browser_session.must_get_current_page()
            
            ctx.logger.info("🔍 Verifying page navigation...")
            
            # Check 1: URL contains reservation indicators
            current_url = await page.get_url()
            ctx.logger.info(f"Current URL: {current_url}")
            
            url_indicators = ['book', 'reserve', 'details', 'checkout', 'reservation']
            url_changed = any(indicator in current_url.lower() for indicator in url_indicators)
            
            # Check 2: Search bar is gone (means we left the search page)
            search_check_js = """
            () => {{
                const searchBar = document.querySelector('[data-test*="search"], input[placeholder*="restaurant"], input[placeholder*="Search"]');
                const timeSlots = document.querySelectorAll('button[data-test*="time"]');
                return {{
                    hasSearchBar: !!searchBar,
                    hasTimeSlots: timeSlots.length > 0
                }};
            }}
            """
            
            page_check = await page.evaluate(search_check_js)
            search_bar_gone = not page_check.get('hasSearchBar', True)
            time_slots_gone = not page_check.get('hasTimeSlots', True)
            
            ctx.logger.info(f"URL changed to reservation page: {url_changed}")
            ctx.logger.info(f"Search bar gone: {search_bar_gone}")
            ctx.logger.info(f"Time slots gone: {time_slots_gone}")
            
            # Determine if we're on the reservation page
            if url_changed or (search_bar_gone and time_slots_gone):
                success_msg = f"""✅ Page Navigation Verified!

You are now on the reservation details page.
- URL: {current_url}
- Search page elements are gone
- Ready to fill reservation form

Proceed to fill the contact information form."""
                
                ctx.logger.info(success_msg)
                return ActionResult(
                    is_done=False,
                    extracted_content=success_msg
                )
            else:
                failure_msg = f"""⚠️ Still on Search/Results Page!

The time slot click did NOT navigate to the reservation page.
- URL: {current_url}
- Search elements still visible

You need to click the time slot button again. Look for a button with a time like "7:00 PM" or "8:00 PM" and click it."""
                
                ctx.logger.warning(failure_msg)
                return ActionResult(
                    is_done=False,
                    extracted_content=failure_msg
                )
                
        except Exception as e:
            error_msg = f"❌ Page Verification Error: {str(e)}"
            ctx.logger.error(error_msg)
            return ActionResult(
                is_done=False,
                extracted_content=error_msg
            )
    
    # Build task with credit card support
    task = f"""Make a complete OpenTable reservation:
follow these exact steps:
STEPS:
1. Go to OpenTable.com

2. MANDATORY: Call the tool "Select date, time, and party size on OpenTable homepage" with:
   - date: "{date}"
   - time: "{time}"
   - party_size: {party_size}
   
   This tool will reliably set all three fields using the correct selectors.
   DO NOT manually click date/time/party size fields - the tool handles it!

3. After the tool completes successfully, enter in search bar: "{restaurant} {location}"

4. Choose a time slot on the restaurant close to {time} any time within 2 hours if exact {time} not available
   
5. MANDATORY: After clicking time slot, call the tool "Verify page navigation to reservation form"
   - This tool checks if the page successfully navigated to the reservation details page
   - If verification FAILS → the time slot click didn't work, try clicking it again
   - If verification SUCCEEDS → proceed to next step
   - DO NOT skip this verification step!
   
6. If you see seating options (indoor/outdoor/bar), choose default and move to next page

7. RESERVATION DETAILS FORM - Fill contact fields based on what's present:
   
   Check the form for these fields and fill accordingly (ONE value per field):
   
   IF "First name" field exists THEN fill it with: {first_name}
   IF "Last name" field exists THEN fill it with: {last_name}
   IF "Phone number" field exists THEN fill it with: {phone}
   IF "Email" field exists THEN fill it with: {email}
   
   IMPORTANT:
   - A field might not exist on the form - that's OK! Only fill fields that are present.
   - Some forms only have phone number, others have all four fields.
   - DO NOT type multiple values into the same field!
   - Each value goes in ITS OWN field only.
   
   What to SKIP:
   - "Occasion (optional)" - skip this
   - "Special request (optional)" - skip this
   - Any dropdown/field marked "(optional)" - skip it
   - Newsletter/marketing checkboxes - leave them as-is
   - "Use email instead" button - DO NOT click this
   
   After filling contact fields, if you see credit card section, proceed to step 8.
   If no credit card section, proceed to step 9.
   
   IMPORTANT FOR PHONE NUMBER:
   - If the phone number starts with a country code (e.g., +44, +91, +61, etc.), you MUST:
     a) First change the country code dropdown to match that country code
     b) Then enter only the remaining digits (without the country code)
   - If no country code is present, assume US (+1) and enter the full number
   - Examples:
     * "+44 7911 123456" -> Select +44 (UK) dropdown, enter "7911123456"
     * "+91 98765 43210" -> Select +91 (India) dropdown, enter "9876543210"
     * "415-555-1234" -> Keep +1 (US) dropdown, enter "4155551234"

8. CREDIT CARD FORM (if present):
   
   If you see credit card fields (Card Number, Name on Card, Expiry Date, CVV, ZIP Code):
   
   STEP 1 (MANDATORY): Call the tool "Fill credit card iframe fields using CDP"
   - This fills Card Number and CVV which are in iframes you cannot access
   
   STEP 2 (AFTER TOOL): Manually fill the 3 main page fields:
   - Name on Card: {CARD_DATA['name on the card']}
   - Expiry Date: {CARD_DATA['expiry_month']}/{CARD_DATA['expiry_year'][-2:]}
   - ZIP Code: {CARD_DATA['zip']}
   
   YOU MUST DO BOTH STEPS!
   
   DO NOT skip the tool call
   DO NOT skip filling the main page fields
   DO NOT give up if one step fails
   
   If you DO NOT see credit card fields at all, skip this step entirely.

9. ACCEPT TERMS AND COMPLETE RESERVATION:
   
   - Find and check the box: "Accept terms and conditions" or similar
   - Click "Complete Reservation" button
   
   AFTER CLICKING:
   - If popup asks "Save this card?" → Click "No thanks"
   - Wait patiently 10-20 seconds for processing
   - DO NOT mark as failed if page is loading
   - DO NOT click button multiple times
   
   What might happen next (be flexible and handle whatever appears):
   - OTP verification page → Go to step 10
   - Modal asking for First/Last/Email → Go to step 11
   - "Invalid card" error → Task SUCCESS (test card expected to fail)
   - Confirmation page → Task SUCCESS!

10. OTP VERIFICATION (if appears):
   
   If you see an OTP/verification code input:
   - Call get_otp_from_human tool to ask human for code
   - Enter the OTP code in input field
   - Page will auto-submit after entering code
   - DO NOT manually click Continue - happens automatically
   - After OTP success, a modal might appear → proceed to step 11
   - Or you might see confirmation page → Task SUCCESS!

11. DETAILS MODAL (if appears after OTP or directly):
   
   If a modal/popup appears with form fields:
   - DO NOT CLOSE THIS MODAL
   - Fill any fields you see:
     * If "First name" field → type: {first_name}
     * If "Last name" field → type: {last_name}
     * If "Email" field → type: {email}
   - Click "Complete reservation" button INSIDE the modal
   - Wait for confirmation page → Task SUCCESS!


CRITICAL: You CAN fill credit cards using the tool! Do NOT mark task as failed!"""
    
    try:
        # Create and run browser agent
        llm = ChatGoogle(model="gemini-2.0-flash-exp")
        browser_agent = BrowserAgent(task=task, llm=llm, tools=tools)
        
        ctx.logger.info("Starting browser automation...")
        result = await browser_agent.run()
        
        ctx.logger.info(f"Browser automation result: {result}")
        
        # Clean up queue
        if sender in OTP_QUEUES:
            del OTP_QUEUES[sender]
        
        return {
            'success': True,
            'message': str(result)
        }
        
    except Exception as e:
        ctx.logger.error(f"Browser automation error: {e}")
        # Clean up queue
        if sender in OTP_QUEUES:
            del OTP_QUEUES[sender]
        
        return {
            'success': False,
            'message': f'Error: {str(e)}'
        }


@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handle incoming chat messages"""
    
    # Send acknowledgement
    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.now(timezone.utc),
        acknowledged_msg_id=msg.msg_id
    ))
    
    # Process message content
    for item in msg.content:
        if isinstance(item, TextContent):
            query_text = item.text.strip()
            ctx.logger.info(f"Query from {sender}: {query_text}")
            
            # Check if we're waiting for OTP
            if sender in OTP_QUEUES:
                ctx.logger.info(f"OTP received: {query_text}")
                await OTP_QUEUES[sender].put(query_text)
                continue
            
            # Extract info with OpenAI
            extraction = await extract_info_with_openai(ctx, query_text)
            
            if extraction['status'] != 'success':
                help_msg = """Hi! I'm your OpenTable reservation assistant.

Examples:
- "Book Amber India tomorrow at 8pm for 4 people"
- "Reserve Che Fico today for 2, John Doe (john@email.com, 415-555-1234)"
- "Book a table at Gary Danko" (I'll use defaults: today, 7:30 PM, 2 people)

I'll handle the rest, including OTP verification and credit card filling!"""
                await ctx.send(sender, create_text_chat(help_msg))
                continue
            
            data = extraction['data']
            
            # Get or create session state
            if sender not in SESSION_STATE:
                SESSION_STATE[sender] = {}
            state = SESSION_STATE[sender]
            
            # Update state with extracted info
            for key in ['restaurant', 'location', 'first_name', 'last_name', 'email', 'phone', 'date', 'time', 'party_size']:
                if data.get(key):
                    state[key] = data[key]
            
            # Check what's missing for booking (date, time, party_size optional with defaults)
            missing = []
            if not state.get('restaurant'):
                missing.append('restaurant name')
            if not state.get('first_name'):
                missing.append('first name')
            if not state.get('last_name'):
                missing.append('last name')
            if not state.get('email'):
                missing.append('email')
            if not state.get('phone'):
                missing.append('phone number')
            
            # Set defaults for optional fields
            if not state.get('date'):
                state['date'] = 'today'
            if not state.get('time'):
                state['time'] = '7:30 PM'
            if not state.get('party_size'):
                state['party_size'] = 2
            
            # If anything is missing, ask for it
            if missing:
                current = []
                if state.get('restaurant'):
                    current.append(f"- Restaurant: {state['restaurant']}")
                if state.get('date'):
                    current.append(f"- Date: {state['date']}")
                if state.get('time'):
                    current.append(f"- Time: {state['time']}")
                if state.get('party_size'):
                    current.append(f"- Party Size: {state['party_size']}")
                if state.get('first_name') and state.get('last_name'):
                    current.append(f"- Name: {state['first_name']} {state['last_name']}")
                if state.get('email'):
                    current.append(f"- Email: {state['email']}")
                if state.get('phone'):
                    current.append(f"- Phone: {state['phone']}")
                
                current_str = "\n".join(current) if current else "Nothing yet"
                missing_str = ", ".join(missing)
                
                ask_msg = f"""I need some more info:

What I have:
{current_str}

Still need: {missing_str}

Please provide the missing details!"""
                await ctx.send(sender, create_text_chat(ask_msg))
                continue
            
            # All info collected - start booking
            restaurant = state['restaurant']
            location = state.get('location', 'San Francisco')
            first_name = state['first_name']
            last_name = state['last_name']
            email = state['email']
            phone = state['phone']
            date = resolve_date(state['date'], location)  # Convert 'today'/'tomorrow' to actual date in restaurant's timezone
            time = state['time']
            party_size = state['party_size']
            
            ctx.logger.info(f"Date resolved: '{state['date']}' -> {date} (location: {location})")
            
            # Format date nicely for display (e.g., "2025-11-03 (today)")
            date_display = date
            if state['date'].lower() == 'today':
                date_display = f"{date} (today in {location})"
            elif state['date'].lower() == 'tomorrow':
                date_display = f"{date} (tomorrow in {location})"
            
            processing_msg = f"""Starting your reservation!

Restaurant: {restaurant} in {location}
Date: {date_display}
Time: {time}
Party Size: {party_size}
Name: {first_name} {last_name}
Email: {email}
Phone: {phone}

Opening browser..."""
            await ctx.send(sender, create_text_chat(processing_msg))
            
            # Run browser automation in background task
            asyncio.create_task(run_reservation_task(ctx, sender, restaurant, location, first_name, last_name, email, phone, date, time, party_size))


@chat_proto.on_message(ChatAcknowledgement)
async def handle_acknowledgement(ctx: Context, sender: str, msg: ChatAcknowledgement):
    """Handle message acknowledgements"""
    ctx.logger.debug(f"Message {msg.acknowledged_msg_id} acknowledged")


# Include the chat protocol
agent.include(chat_proto, publish_manifest=True)


if __name__ == "__main__":
    print("OpenTable Reservation Agent - ASI1 with Card Tool")
    print(f"Agent address: {agent.address}")
    print(f"Gemini: {'Configured' if GEMINI_API_KEY else 'Not configured'}")
    print(f"OpenAI: {'Configured' if OPENAI_API_KEY else 'Not configured'}")
    print("\nReady for ASI1 connections with:")
    print("- Async OTP support")
    print("- CDP-based credit card iframe filling")
    
    agent.run()
