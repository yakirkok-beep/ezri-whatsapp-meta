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

# === מעקב אחרי משתמשים שכבר קיבלו ברכת שבוע תנועה (פעם אחת בשבוע) ===
movement_week_greeted = set()


# ============================================================
# טעינת מאגר הידע הנוסף (דמויות, ועידה, שבוע תנועה)
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
            context += f"- {topic['name']}: {topic.get('summary', '')}\n"
        context += "\n"

    figures = KNOWLEDGE_EXTRA.get("movement_figures", [])
    if figures:
        context += "## דמויות מרכזיות בתנועה:\n"
        for fig in figures:
            context += f"\n### {fig['name']} ({fig.get('years', '')})\n"
            context += f"תפקיד: {fig.get('role', '')}\n"
            if fig.get("core_principles"):
                context += "עקרונות מרכזיים:\n"
                for p in fig["core_principles"][:3]:
                    context += f"- {p}\n"
            if fig.get("connection_to_ezra"):
                context += f"קשר לעזרא: {fig['connection_to_ezra']}\n"

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
🔟 👥 דמויות התנועה
1️⃣1️⃣ 📚 ועידת התנועה

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
- 10 = חובה להשתמש רק בדמויות מתוך הרשימה במידע הנוסף למטה (חמש הדמויות במאגר). אסור להמציא או להוסיף דמויות אחרות. הצג את חמש הדמויות בלבד עם מספור 1-5, ושאל על איזו ללמוד.
- 11 = חובה להשתמש רק בששת הנושאים מהועידה במידע הנוסף למטה. אסור להמציא נושאים אחרים. הצג את ששת הנושאים בלבד עם מספור 1-6, ושאל באיזה נושא להעמיק.
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

# הוספת ההקשר הנוסף (דמויות + ועידה) ל-system prompt
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

    # 0 = main menu + clear history
    if text == "0":
        conversation_history[phone] = []
        return greeting_prefix + MAIN_MENU

    # Greetings = main menu + clear history
    if text.lower() in GREETINGS or text in GREETINGS:
        conversation_history[phone] = []
        return greeting_prefix + MAIN_MENU

    # Help/menu
    if text in {"עזרה", "תפריט", "help", "menu"}:
        return greeting_prefix + MAIN_MENU

    # Reset
    if text in {"אפס", "מחק", "reset"}:
        conversation_history[phone] = []
        return greeting_prefix + "🔄 מתחילים מחדש!\n\n" + MAIN_MENU

    # Everything else goes to Claude with history
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
