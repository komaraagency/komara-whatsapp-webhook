# Komara Agency — Passerelle Webhook WhatsApp

Serveur prêt pour Railway qui reçoit les messages WhatsApp Cloud API,
valide la signature Meta et peut répondre automatiquement.

## 1. Déployer sur Railway

1. railway.app → *New Project* → *Deploy from GitHub repo* → `komara-whatsapp-webhook`
2. Railway détecte le `Dockerfile` et déploie seul.
3. Dans *Variables*, ajoute :

| Variable | Obligatoire | Rôle |
|---|---|---|
| `VERIFY_TOKEN` | oui | Mot de passe libre, à recopier à l'identique dans Meta |
| `APP_SECRET` | recommandé | Secret de l'app Meta, valide les signatures |
| `WHATSAPP_TOKEN` | pour répondre | Token permanent du système |
| `PHONE_NUMBER_ID` | pour répondre | Identifiant du numéro d'envoi |
| `AUTO_REPLY` | non | `1` = message de bienvenue automatique |
| `ADMIN_KEY` | non | Protège la route `/messages` |

4. Ouvre `https://ton-service.up.railway.app/health` pour confirmer que le service vit.

## 2. Brancher dans Meta

Dans *WhatsApp → Configuration → Webhook* :

- URL de rappel : `https://ton-service.up.railway.app/webhook`
- Token de vérification : exactement la valeur de `VERIFY_TOKEN`
- Clique *Vérifier et enregistrer*
- Abonne-toi au champ `messages`

## 3. Routes

- `GET /health` — état du service
- `GET /webhook` — vérification Meta
- `POST /webhook` — réception des messages
- `GET /messages` — derniers messages reçus (ajoute `?key=ADMIN_KEY`)

## Notes

- La route répond toujours `200` vite à Meta, sinon Meta réessaie en boucle.
- Les 100 derniers messages restent en mémoire : redémarrage = journal vidé.
- Pour un historique durable, branche une base de données ou un volume.
