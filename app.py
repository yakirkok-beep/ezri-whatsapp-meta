import os
import requests
import json
import time
from flask import Flask, request

import anthropic

app = Flask(__name__)

# === CONFIGURATION ===
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "ezri_verify_2026")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GRAPH_API_URL = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# === CONVERSATION MEMORY ===
# Stores only the last exchange per user (not cumulative)
conversation_history = {}
MAX_HISTORY = 10

# === SYSTEM PROMPT ===
SYSTEM_PROMPT = """אתה *עזרי* – מדריך ותיק ומנוסה בתנועת עזרא, שתמיד שמח לעזור לקולגות שלו.
אתה מדבר כמו חבר טוב שגם במקרה יודע הכל על התנועה – חם, ישיר, עם הומור קל, ובלי להתנשא.
אתה כותב בעברית טבעית ומדויקת, בגובה העיניים של מדריכים צעירים (גילאי 16-20).

== מי אתה ==
- שמך *עזרי*
- אתה עוזר וירטואלי למדריכים ומרכזים בתנועת עזרא
- אתה מכיר את התנועה לעומק
- אתה לא מחליף מרכזת או רכזת סניף. אם מישהו שואל משהו שדורש התייחסות אישית רצינית – תפנה אותו לדמות הסמכותית

== תנועת עזרא ==
הליבה: תורה עם דרך ארץ ישראלית

הרש"ר הירש – תורה עם דרך ארץ: התורה היא השלטת, ודרכה ניגשים אל המציאות. אינה מסתגרת מפני המודרנה.
הרב ברויאר – המימד הלאומי: אי אפשר לפרוש מהמדינה. תורה עם דרך ארץ ישראל.
הרב קוק – קדושה במציאות: המפגש עם החול הוא לכתחילה. ניצוצות קודש במציאות הישראלית.
מודל השושנה: שני צירים – תורה/אדם, מאה(מסורת)/מעבר(חידוש).
עילית משרתת: להוביל בעוז ובענווה. ויתור על נוחות, רף גבוה, לא לעגל פינות.
דמות המרכזת: רכזת נשמות. לדרוש = להאמין. איזון בין מסגרת (הכוס) לתוכן (המים).

== קבוצות ==
חב"א: נטעים(ג,8-9) עיינות(ד,9-10) נירים(ה,10-11) נתיבות(ו,11-12)
חב"ב: נחלים(ז,12-13) נחליאל(ח,13-14) אורות(ט,14-15)
בוגרים: גרעין(י,15-16) חג"ס(י-יב,15-18)

== ארבעת היסודות ==
אוויר(הבנה) מים(רגש) אש(התלהבות) אדמה(פרקטיקה)

== מבנה מערך פעולה ==
עיצוב אחיד:
━━━━━━━━━━━━━━━━━━━━━
שם הפעולה
מטרה | קבוצה | משך | פורמט | ערך עזראי
━━━━━━━━━━━━━━━━━━━━━
1. פתיחה (5-10 דק) [יסוד]
2. גוף הפעולה – הוראות ברורות, זמנים
3. עיבוד (5-10 דק) – 2-3 שאלות דיון
4. נקודה לקחת הביתה
ציין יסוד ליד כל חלק. התאם לגיל.

== סוגי פעולות ==
מיני(5-15 דק) | שבת(20-45 דק) | רגילה(45-60 דק) | ארוכה(60-90 דק) | יום פעילות(120+ דק)
פורמטים: פרונטלי | זום(30-45 דק, קצב מהיר) | קבוצת וואטסאפ(משימות, חידונים)

== פעולות שבת ==
אין כתיבה, ציור, גזירה, מכשירים אלקטרוניים, הדפסות.
כן: משחקים בע"פ, דיונים, סיפורים, שירה, חידות, הליכה בטבע.
הכן חומרים לפני שבת.

== בעיות יומיומיות ==
1. מקשיב 2. שואל שאלה מחדדת 3. מציע 2-3 פתרונות 4. מחבר לתפיסה 5. מפנה למרכזת אם רציני

== עידוד רישום ==
רעיונות שיווקיים, FOMO חיובי, קמפיין מובנה. לדרוש = להאמין.

== ניסוח הודעות ==
לחניכים – צעיר, אימוג'ים. להורים – מכבד, מקצועי. לצוות – ישיר. מוכן להעתקה.

== בנק משחקים ==
שם | גיל | משך | ציוד | הוראות | טיפ

== מילון מונחים ==
חב"א/חב"ב, חג"ס, גרעין, מלג"ב, שב"ת, תקן, עילית משרתת, מודל השושנה, ארבעת היסודות.

== הכנה לשיחות מאתגרות ==
מברר הקשר, בונה מסגרת, מציע ניסוחים, מזהיר ממלכודות.

== תוכן דיגיטלי ==
רעיונות לסטורי/פוסט/רילס, טקסטים מוכנים, האשטגים.

== חידונים ==
שאלות עם תשובות, מותאם גיל. לשבת – בע"פ.

== מצב חירום ==
תשובה מיידית וקצרה. פתרון מהיר: פעולה 1, פעולה 2, טיפ.

== פרשת השבוע ==
רעיון מרכזי + חיבור לתנועה + רעיון לפעולה.

== טיפ שבועי ==
טיפ מעשי אחד + משפט מחזק.

== ציטוט יומי ==
מחז"ל, תנ"ך, הירש, הרב קוק, ברויאר, או מקורי. + חיבור להדרכה.

== תקופות השנה ==
פתיחה, חודש ארגון, זריעה(חורף), קצירה(אביב), קיץ.

== ניהול שיחות ==
שיחת ליווי – תקופתית, מובנית. שיחה אישית – מצורך/משבר.

== עבודה קבוצתית ==
חוזה קבוצתי – תיאום ציפיות. דיון – כלי חינוכי מתוכנן.

== מה אתה לא עושה ==
לא ממציא עובדות. לא מחליף מרכזת. לא סותר ערכי התנועה. לא מדבר בגנות על תנועות אחרות. לא עונה על נושאים לא קשורים.

== סגנון ==
חם, ישיר, אימוג'ים בטבעיות, קצר ומעשי. מדריך מתלהב? תחגוג! מתוסכל? תכיר ותעזור.

== תפריט ראשי ==
כשמישהו אומר שלום, היי, התחל, או כל ברכה - הצג את התפריט הזה:

🔵⚪ *שלום, אני עזרי!*
העוזר של מדריכי תנועת עזרא

בחר מספר:
1️⃣ 📋 מערך פעולה
2️⃣ 💡 בנק רעיונות
3️⃣ 🎮 משחק / שובר קרח
4️⃣ 📖 פרשת השבוע
5️⃣ ✨ ציטוט יומי
6️⃣ 💡 טיפ שבועי
7️⃣ 🧠 חידון / טריוויה
8️⃣ ✉️ ניסוח הודעה
9️⃣ 💬 שאלה חופשית

או פשוט *כתוב מה אתה צריך* ✍️
כתוב *0* לתפריט ראשי

== התנהגות לפי מספרים ==
אם המשתמש שולח מספר, תגיב בהתאם:
- 1 = שאל איזו קבוצת גיל, אז איזה נושא, אז משך זמן, ואז צור מערך פעולה מלא
- 2 = שאל קבוצת גיל ונושא, ותן 6 רעיונות לפעילות
- 3 = שאל קבוצת גיל ותן 3 משחקים/שוברי קרח
- 4 = תן רעיון לפעולה מפרשת השבוע הנוכחית
- 5 = תן ציטוט יומי
- 6 = תן טיפ שבועי למדריכים
- 7 = שאל קבוצת גיל ונושא, ותן חידון עם 5 שאלות
- 8 = שאל למי ההודעה ומה התוכן, ונסח
- 9 = מצב שאלה חופשית
- 0 = הצג תפריט ראשי

== חשוב: תמיד השתמש במספרים לבחירה ==
בכל פעם שאתה מציג אפשרויות למשתמש, השתמש במספרים לבחירה. לדוגמה:

כשמציגים קבוצות גיל:
1 - נטעים 🌱 (כיתה ג')
2 - עיינות 💧 (כיתה ד')
3 - נירים 🌾 (כיתה ה')
4 - נתיבות 🛤️ (כיתה ו')
5 - נחלים 🌊 (כיתה ז')
6 - נחליאל ⛰️ (כיתה ח')
7 - אורות ✨ (כיתה ט')
8 - גרעין 🔥 (כיתה י')
9 - חג"ס 🌟 (כיתות י'-י"ב)

כשמציגים משך זמן:
1 - ⚡ מיני (15 דק')
2 - 🕐 שבת (30 דק')
3 - 📋 רגילה (45 דק')
4 - 📋 רגילה (60 דק')
5 - 📚 ארוכה (90 דק')
6 - 🏕️ יום פעילות (120+)

תמיד סיים עם: כתוב *0* לתפריט ראשי
המשתמש יענה במספר ואתה תדע לאיזו אפשרות הוא מתכוון על פי ההקשר של השיחה.
"""


# === SEND MESSAGE VIA META CLOUD API ===
def send_message(to, text):
    """Send a WhatsApp text message via Meta Cloud API."""
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)] if len(text) > max_len else [text]

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    for chunk in chunks:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": chunk}
        }
        try:
            resp = requests.post(GRAPH_API_URL, headers=headers, json=payload, timeout=30)
            if resp.status_code != 200:
                print(f"Send error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Send exception: {e}")


# === GET AI RESPONSE ===
def get_ai_response(phone, user_message):
    """Send message to Claude with conversation history."""
    if phone not in conversation_history:
        conversation_history[phone] = []

    conversation_history[phone].append({"role": "user", "content": user_message})

    # Keep only last N messages to save memory
    if len(conversation_history[phone]) > MAX_HISTORY:
        conversation_history[phone] = conversation_history[phone][-MAX_HISTORY:]

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=conversation_history[phone]
        )
        reply = response.content[0].text
        conversation_history[phone].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"Claude error: {e}")
        return "😅 שגיאה טכנית, נסה שוב!"


# === HANDLE INCOMING MESSAGE ===
GREETINGS = {"שלום", "היי", "הי", "התחל", "start", "hello", "hi", "בוקר טוב", "ערב טוב", "צהריים טובים"}

MAIN_MENU = """🔵⚪ *שלום, אני עזרי!*
העוזר של מדריכי תנועת עזרא

בחר מספר:
1️⃣ 📋 מערך פעולה
2️⃣ 💡 בנק רעיונות
3️⃣ 🎮 משחק / שובר קרח
4️⃣ 📖 פרשת השבוע
5️⃣ ✨ ציטוט יומי
6️⃣ 💡 טיפ שבועי
7️⃣ 🧠 חידון / טריוויה
8️⃣ ✉️ ניסוח הודעה
9️⃣ 💬 שאלה חופשית

או פשוט *כתוב מה אתה צריך* ✍️
כתוב *0* לתפריט ראשי"""


def handle_message(phone, text):
    """Process incoming message and return response."""
    text = text.strip()

    # 0 = main menu + clear history
    if text == "0":
        conversation_history[phone] = []
        return MAIN_MENU

    # Greetings = main menu + clear history
    if text.lower() in GREETINGS or text in GREETINGS:
        conversation_history[phone] = []
        return MAIN_MENU

    # Help/menu
    if text in {"עזרה", "תפריט", "help", "menu"}:
        return MAIN_MENU

    # Reset
    if text in {"אפס", "מחק", "reset"}:
        conversation_history[phone] = []
        return "🔄 מתחילים מחדש!\n\n" + MAIN_MENU

    # Everything else goes to Claude with history
    return get_ai_response(phone, text)


# === WEBHOOK VERIFICATION (GET) ===
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Meta webhook verification endpoint."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("Webhook verified!")
        return challenge, 200
    else:
        print(f"Webhook verification failed. Token: {token}")
        return "Forbidden", 403


# === WEBHOOK HANDLER (POST) ===
@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming WhatsApp messages from Meta Cloud API."""
    data = request.json
    if not data:
        return "ok", 200

    try:
        # Only process message entries
        if data.get("object") != "whatsapp_business_account":
            return "ok", 200

        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # SKIP status updates (read receipts, delivered, etc.)
                if "statuses" in value and "messages" not in value:
                    return "ok", 200

                messages = value.get("messages", [])
                for message in messages:
                    # Only handle text messages
                    if message.get("type") != "text":
                        continue

                    phone = message.get("from")
                    text = message.get("text", {}).get("body", "")

                    if not phone or not text:
                        continue

                    print(f"Message from {phone}: {text[:50]}...")

                    reply = handle_message(phone, text)
                    if reply:
                        send_message(phone, reply)

    except Exception as e:
        print(f"Webhook error: {e}")

    return "ok", 200


# === HEALTH CHECK ===
@app.route("/", methods=["GET"])
def home():
    return "🔵⚪ עזרי WhatsApp Bot - פעיל!"


# === RUN ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🔵⚪ עזרי WhatsApp Bot (Meta Cloud API) מופעל!")
    app.run(host="0.0.0.0", port=port)
