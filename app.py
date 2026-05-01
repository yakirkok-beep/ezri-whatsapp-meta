import os
import requests
import json
import time
from datetime import date, datetime
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
conversation_history = {}
MAX_HISTORY = 10

# === מעקב אחרי משתמשים שכבר קיבלו ברכת שבוע תנועה ===
movement_week_greeted = set()

# === מצב נוכחי של משתמש ===
user_mode = {}


# ============================================================
# טעינת מאגר הידע הנוסף
# ============================================================

KNOWLEDGE_EXTRA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "knowledge_extra.json"
)


def load_knowledge_extra():
    """טוען את קובץ ה-JSON של התוכן הנוסף"""
    try:
        with open(KNOWLEDGE_EXTRA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARN] knowledge_extra.json not found at {KNOWLEDGE_EXTRA_PATH}")
        return {}
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
        return {}


KNOWLEDGE_EXTRA = load_knowledge_extra()


def is_movement_week():
    """בודק אם היום בתוך שבוע התנועה"""
    mw = KNOWLEDGE_EXTRA.get("movement_week", {})
    if not mw.get("active"):
        return False
    try:
        start = datetime.strptime(mw["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(mw["end_date"], "%Y-%m-%d").date()
        return start <= date.today() <= end
    except (KeyError, ValueError):
        return False


def get_movement_week_greeting():
    """מחזיר את ברכת שבוע התנועה"""
    if not is_movement_week():
        return ""
    return KNOWLEDGE_EXTRA.get("movement_week", {}).get("greeting", "")


def build_extra_context_for_claude():
    """מחזיר טקסט להוסיף ל-system prompt"""
    context = "\n\n=== מידע נוסף לעזרי ===\n\n"

    conf = KNOWLEDGE_EXTRA.get("conference_2026", {})
    if conf:
        context += f"## ועידת התנועה הנוכחית: {conf.get('title', '')}\n"
        context += f"{conf.get('description', '')}\n\n"
        context += "נושאי הועידה:\n"
        for topic in conf.get("topics", []):
            context += f"\n### {topic['name']}\n"
            context += f"{topic.get('summary', '')}\n"
            if topic.get('key_questions'):
                context += "שאלות מפתח: " + " | ".join(topic['key_questions']) + "\n"
            if topic.get('activities_ideas'):
                context += "רעיונות לפעולה: " + " | ".join(topic['activities_ideas']) + "\n"
            if topic.get('connection_to_thinkers'):
                context += f"חיבור להוגי התנועה: {topic['connection_to_thinkers']}\n"
        context += "\n"

    figures = KNOWLEDGE_EXTRA.get("movement_figures", [])
    if figures:
        context += "## דמויות מרכזיות בתנועה:\n"
        for fig in figures:
            context += f"\n### {fig['name']} ({fig.get('years', '')})\n"
            context += f"תפקיד: {fig.get('role', '')}\n"
            context += f"רקע: {fig.get('biography', '')}\n"
            if fig.get("core_principles"):
                context += "עקרונות מרכזיים: " + " | ".join(fig['core_principles']) + "\n"
            if fig.get("key_quotes"):
                context += "ציטוטים: " + " | ".join(fig['key_quotes']) + "\n"
            if fig.get("connection_to_ezra"):
                context += f"קשר לעזרא: {fig['connection_to_ezra']}\n"
            if fig.get("fun_fact"):
                context += f"עובדה מעניינת: {fig['fun_fact']}\n"

    if is_movement_week():
        context += "\n## שים לב: השבוע הוא שבוע התנועה!\n"
        context += "השתדל לחבר תשובות לרוח שבוע התנועה ולנושאי הועידה.\n"

    return context


# === SYSTEM PROMPT ===
SYSTEM_PROMPT_BASE = """אתה *עזרי* – מדריך ותיק ומנוסה בתנועת עזרא, שתמיד שמח לעזור לקולגות שלו.
אתה מדבר כמו חבר טוב שגם במקרה יודע הכל על התנועה – חם, ישיר, עם הומור קל, ובלי להתנשא.
אתה כותב בעברית טבעית ומדויקת, בגובה העיניים של מדריכים צעירים (גילאי 16-20).

== מי אתה ==
- שמך *עזרי*
- אתה עוזר וירטואלי למדריכים ומרכזים בתנועת עזרא
- אתה מכיר את התנועה לעומק
- אתה לא מחליף מרכזת או רכזת סניף

== תנועת עזרא ==
הליבה: תורה עם דרך ארץ ישראלית
הרש"ר הירש – תורה עם דרך ארץ
הרב ברויאר – המימד הלאומי: תורה עם דרך ארץ ישראל
הרב קוק – קדושה במציאות
מודל השושנה: שני צירים – תורה/אדם, מאה/מעבר
עילית משרתת: להוביל בעוז ובענווה
דמות המרכזת: רכזת נשמות. לדרוש = להאמין

== קבוצות ==
חב"א: נטעים(ג) עיינות(ד) נירים(ה) נתיבות(ו)
חב"ב: נחלים(ז) נחליאל(ח) אורות(ט)
בוגרים: גרעין(י) חג"ס(י-יב)

== ארבעת היסודות ==
אוויר(הבנה) מים(רגש) אש(התלהבות) אדמה(פרקטיקה)

== מבנה מערך פעולה ==
שם הפעולה | מטרה | קבוצה | משך | פורמט | ערך עזראי
1. פתיחה (5-10 דק) [יסוד]
2. גוף הפעולה
3. עיבוד (5-10 דק)
4. נקודה לקחת הביתה

== סוגי פעולות ==
מיני(5-15 דק) | שבת(20-45 דק) | רגילה(45-60 דק) | ארוכה(60-90 דק) | יום פעילות(120+)
פורמטים: פרונטלי | זום(קצב מהיר) | קבוצת וואטסאפ

== פעולות שבת ==
אין: כתיבה, ציור, גזירה, מכשירים אלקטרוניים, הדפסות.
כן: משחקים בע"פ, דיונים, סיפורים, שירה, חידות, הליכה בטבע.

== ניסוח הודעות ==
לחניכים – צעיר, אימוג'ים. להורים – מכבד. לצוות – ישיר. מוכן להעתקה.

== מה אתה לא עושה ==
לא ממציא עובדות. לא מחליף מרכזת. לא סותר ערכי התנועה.

== סגנון ==
חם, ישיר, אימוג'ים בטבעיות, קצר ומעשי.

== תפריט ראשי ==
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
🔟 👥 דמויות התנועה
1️⃣1️⃣ 📚 ועידת התנועה

או פשוט *כתוב מה אתה צריך* ✍️
כתוב *0* לתפריט ראשי

== התנהגות לפי מספרים ==
- 1 = שאל איזו קבוצת גיל, נושא, משך זמן, ואז צור מערך פעולה
- 2 = שאל קבוצת גיל ונושא, ותן 6 רעיונות לפעילות
- 3 = שאל קבוצת גיל ותן 3 משחקים
- 4 = רעיון לפעולה מפרשת השבוע
- 5 = ציטוט יומי
- 6 = טיפ שבועי
- 7 = חידון עם 5 שאלות
- 8 = שאל למי ההודעה ונסח
- 9 = מצב שאלה חופשית
- 0 = הצג תפריט ראשי

== חשוב מאוד: דמויות תנועה ונושאי ועידה ==
כשמשתמשים שואלים על דמות תנועה, השתמש *רק* במידע שמופיע למטה במידע הנוסף. אל תוסיף דמויות אחרות, אל תמציא עובדות.
כשמשתמשים שואלים על נושא ועידה — השתמש רק בששת הנושאים מהמידע למטה.

== כשמציגים קבוצות גיל ==
1 - נטעים 🌱 (כיתה ג')
2 - עיינות 💧 (כיתה ד')
3 - נירים 🌾 (כיתה ה')
4 - נתיבות 🛤️ (כיתה ו')
5 - נחלים 🌊 (כיתה ז')
6 - נחליאל ⛰️ (כיתה ח')
7 - אורות ✨ (כיתה ט')
8 - גרעין 🔥 (כיתה י')
9 - חג"ס 🌟 (י'-י"ב)

תמיד סיים עם: כתוב *0* לתפריט ראשי
"""

SYSTEM_PROMPT = SYSTEM_PROMPT_BASE + build_extra_context_for_claude()
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
🔟 👥 דמויות התנועה
1️⃣1️⃣ 📚 ועידת התנועה

או פשוט *כתוב מה אתה צריך* ✍️
כתוב *0* לתפריט ראשי"""


def handle_message(phone, text):
    """Process incoming message and return response."""
    text = text.strip()

    # === ברכת שבוע התנועה — פעם ראשונה בשבוע לכל משתמש ===
    greeting_prefix = ""
    if is_movement_week() and phone not in movement_week_greeted:
        greeting_prefix = get_movement_week_greeting()
        movement_week_greeted.add(phone)

    # 0 = תפריט ראשי + איפוס
    if text == "0":
        conversation_history[phone] = []
        user_mode[phone] = None
        return greeting_prefix + MAIN_MENU

    # ברכות = תפריט ראשי + איפוס
    if text.lower() in GREETINGS or text in GREETINGS:
        conversation_history[phone] = []
        user_mode[phone] = None
        return greeting_prefix + MAIN_MENU

    # עזרה/תפריט
    if text in {"עזרה", "תפריט", "help", "menu"}:
        return greeting_prefix + MAIN_MENU

    # איפוס
    if text in {"אפס", "מחק", "reset"}:
        conversation_history[phone] = []
        user_mode[phone] = None
        return greeting_prefix + "🔄 מתחילים מחדש!\n\n" + MAIN_MENU

    # 10 = רשימת דמויות התנועה
    if text == "10":
        figures = KNOWLEDGE_EXTRA.get("movement_figures", [])
        if not figures:
            return greeting_prefix + "אין מידע זמין על דמויות התנועה כרגע."
        user_mode[phone] = "figures"
        msg = "👥 *דמויות התנועה*\n\nבחר דמות ללמידה עליה:\n\n"
        for i, fig in enumerate(figures, 1):
            msg += f"{i}️⃣ *{fig.get('name', '')}*\n"
            msg += f"   _{fig.get('role', '')}_\n\n"
        msg += "כתוב מספר 1-5 או את שם הדמות.\n\n"
        msg += "כתוב *0* לתפריט ראשי"
        return greeting_prefix + msg

    # 11 = נושאי הועידה
    if text == "11":
        conf = KNOWLEDGE_EXTRA.get("conference_2026", {})
        topics = conf.get("topics", [])
        if not topics:
            return greeting_prefix + "אין מידע זמין על הועידה כרגע."
        user_mode[phone] = "topics"
        msg = f"📚 *{conf.get('title', 'ועידת התנועה')}*\n"
        msg += f"_{conf.get('tagline', '')}_\n\n"
        msg += "בחר נושא להעמיק בו:\n\n"
        for i, topic in enumerate(topics, 1):
            msg += f"{i}️⃣ *{topic.get('name', '')}*\n"
        msg += "\nכתוב מספר 1-6 או את שם הנושא.\n\n"
        msg += "כתוב *0* לתפריט ראשי"
        return greeting_prefix + msg

    # מצב "בחירת דמות" — מספר 1-5 בוחר את הדמות
    if user_mode.get(phone) == "figures" and text in {"1", "2", "3", "4", "5"}:
        figures = KNOWLEDGE_EXTRA.get("movement_figures", [])
        idx = int(text) - 1
        if 0 <= idx < len(figures):
            user_mode[phone] = None
            figure_name = figures[idx].get("name", "")
            response = get_ai_response(phone, f"ספר לי בעומק על {figure_name} — השתמש רק במידע שיש לך עליה במידע הנוסף.")
            return greeting_prefix + response

    # מצב "בחירת נושא ועידה" — מספר 1-6 בוחר את הנושא
    if user_mode.get(phone) == "topics" and text in {"1", "2", "3", "4", "5", "6"}:
        topics = KNOWLEDGE_EXTRA.get("conference_2026", {}).get("topics", [])
        idx = int(text) - 1
        if 0 <= idx < len(topics):
            user_mode[phone] = None
            topic_name = topics[idx].get("name", "")
            response = get_ai_response(phone, f"ספר לי בעומק על נושא הועידה '{topic_name}' — השתמש רק במידע שיש לך עליו.")
            return greeting_prefix + response

    # כל השאר הולך ל-Claude
    response = get_ai_response(phone, text)
    return greeting_prefix + response


# === WEBHOOK VERIFICATION (GET) ===
@app.route("/webhook", methods=["GET"])
def verify_webhook():
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
    data = request.json
    if not data:
        return "ok", 200

    try:
        if data.get("object") != "whatsapp_business_account":
            return "ok", 200

        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                if "statuses" in value and "messages" not in value:
                    return "ok", 200

                messages = value.get("messages", [])
                for message in messages:
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
    movement_week_status = "🎉 שבוע תנועה פעיל!" if is_movement_week() else ""
    return f"🔵⚪ עזרי WhatsApp Bot - פעיל! {movement_week_status}"


# === RUN ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🔵⚪ עזרי WhatsApp Bot (Meta Cloud API) מופעל!")
    if is_movement_week():
        print("🎉 שבוע התנועה פעיל - ברכות יישלחו אוטומטית!")
    app.run(host="0.0.0.0", port=port)
