"""
Komara Agency — Passerelle Webhook WhatsApp Cloud API.

- GET  /webhook  : vérification Meta (hub.mode / hub.verify_token / hub.challenge)
- POST /webhook  : réception des messages, contrôle de signature, journal
- GET  /health   : sonde de santé pour Railway
- GET  /messages : derniers messages reçus (protégé par ADMIN_KEY)

Variables d'environnement :
  VERIFY_TOKEN      token de vérification défini aussi dans Meta (obligatoire)
  APP_SECRET        secret de l'app Meta pour valider les signatures (recommandé)
  WHATSAPP_TOKEN    token permanent pour répondre (optionnel)
  PHONE_NUMBER_ID   identifiant du numéro d'envoi (optionnel)
  AUTO_REPLY        "1" pour répondre automatiquement au premier message
  ADMIN_KEY         clé d'accès à /messages
  PORT              port d'écoute (Railway le fournit)
"""

import hashlib
import hmac
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("komara.webhook")

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
APP_SECRET = os.environ.get("APP_SECRET", "")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
AUTO_REPLY = os.environ.get("AUTO_REPLY", "0") == "1"
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

app = FastAPI(title="Komara WhatsApp Webhook")

MESSAGES = deque(maxlen=100)
SEEN_USERS = set()

BIENVENUE = (
    "Salut et bienvenue chez Komara Agency 🇬🇳\n"
    "Ici Aya, l'assistante de l'agence.\n"
    "Dis-moi ce que tu veux automatiser dans ton business et je t'oriente 😊"
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "komara-whatsapp-webhook",
        "verify_token_configured": bool(VERIFY_TOKEN),
        "signature_check": bool(APP_SECRET),
        "auto_reply": AUTO_REPLY,
        "received": len(MESSAGES),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/", response_class=PlainTextResponse)
async def root():
    return "Komara Agency — webhook WhatsApp actif."


@app.get("/webhook", response_class=PlainTextResponse)
async def verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Meta appelle cette route une fois pour valider l'URL."""
    if not VERIFY_TOKEN:
        log.error("VERIFY_TOKEN absent : impossible de valider le webhook")
        return PlainTextResponse("VERIFY_TOKEN non configuré sur le serveur", status_code=500)

    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        log.info("Webhook vérifié par Meta")
        return PlainTextResponse(hub_challenge)

    log.warning("Échec de vérification (mode=%s)", hub_mode)
    return PlainTextResponse("Verification failed", status_code=403)


def signature_valide(corps: bytes, entete: str) -> bool:
    if not APP_SECRET:
        return True
    if not entete or not entete.startswith("sha256="):
        return False
    attendu = hmac.new(APP_SECRET.encode(), corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, entete.replace("sha256=", "", 1))


def envoyer_message(destinataire: str, texte: str) -> None:
    """Réponse via WhatsApp Cloud API (optionnelle)."""
    if not (WHATSAPP_TOKEN and PHONE_NUMBER_ID):
        return
    try:
        r = requests.post(
            f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages",
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": destinataire,
                "type": "text",
                "text": {"body": texte},
            },
            timeout=15,
        )
        r.raise_for_status()
        log.info("Réponse envoyée à %s", destinataire)
    except Exception as e:  # noqa: BLE001
        log.error("Envoi impossible vers %s : %s", destinataire, e)


def traiter_message(value: dict) -> None:
    for msg in value.get("messages", []) or []:
        expediteur = msg.get("from", "")
        type_msg = msg.get("type", "inconnu")
        texte = ""
        if type_msg == "text":
            texte = msg.get("text", {}).get("body", "")
        elif type_msg in ("button", "interactive"):
            texte = json.dumps(msg.get(type_msg, {}), ensure_ascii=False)

        MESSAGES.append(
            {
                "de": expediteur,
                "nom": (value.get("contacts") or [{}])[0].get("profile", {}).get("name", ""),
                "type": type_msg,
                "texte": texte,
                "recu_le": datetime.now(timezone.utc).isoformat(),
            }
        )
        log.info("Message de %s (%s) : %s", expediteur, type_msg, texte[:200])

        if AUTO_REPLY and expediteur not in SEEN_USERS:
            SEEN_USERS.add(expediteur)
            envoyer_message(expediteur, BIENVENUE)


@app.post("/webhook")
async def recevoir(request: Request):
    corps = await request.body()
    if not signature_valide(corps, request.headers.get("X-Hub-Signature-256", "")):
        log.warning("Signature invalide, requête rejetée")
        return JSONResponse({"error": "invalid signature"}, status_code=403)

    try:
        data = json.loads(corps or b"{}")
    except json.JSONDecodeError:
        log.warning("Corps JSON illisible")
        return JSONResponse({"error": "invalid json"}, status_code=400)

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("messages"):
                traiter_message(value)

    return {"status": "received"}


@app.get("/messages")
async def messages(key: str = ""):
    if ADMIN_KEY and key != ADMIN_KEY:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return {"count": len(MESSAGES), "messages": list(reversed(MESSAGES))}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
