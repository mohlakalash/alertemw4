import os
import re
import json
import smtplib
import requests
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from playwright.sync_api import sync_playwright

EMAIL_ADRESSE = os.environ.get("EMAIL_ADRESSE")
EMAIL_MDP = os.environ.get("EMAIL_MDP")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

URL_PRODUIT = "https://www.allkeyshop.com/blog/buy-call-of-duty-modern-warfare-4-steam-account-compare-prices/"
SEUIL_APPEL = 40.00  # 📞 Votre seuil d'alerte pour MW4
FICHIER_MEMOIRE = "memoire_mw4.json"

def envoyer_email_recap(prix_min, releves):
    if not EMAIL_ADRESSE or not EMAIL_MDP:
        print("⚠️ Erreur : EMAIL_ADRESSE ou EMAIL_MDP manquant.")
        return

    lignes_detail = "\n".join([f"- {r['heure']} : {r['prix']:.2f} €" for r in releves])

    msg = EmailMessage()
    msg["Subject"] = f"mw4 : {prix_min:.2f} euros"
    msg["From"] = EMAIL_ADRESSE.strip()
    msg["To"] = EMAIL_ADRESSE.strip()
    msg.set_content(
        f"Bonjour,\n\n"
        f"Voici le récapitulatif de l'heure écoulée pour Call of Duty Modern Warfare 4 (Compte Steam) :\n\n"
        f"🏆 Prix minimum observé sur l'heure : {prix_min:.2f} €\n\n"
        f"📊 Détail des relevés (toutes les 5 min) :\n{lignes_detail}\n\n"
        f"Lien direct vers l'offre :\n{URL_PRODUIT}"
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADRESSE.strip(), EMAIL_MDP.replace(" ", "").strip())
        smtp.send_message(msg)
    print(f"📧 E-mail récapitulatif horaire MW4 envoyé (Min : {prix_min:.2f} €) !")

def envoyer_message_telegram(prix, nom_jeu):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant dans les Secrets.")
        return

    message = f"🚨 Alerte prix ! Le jeu {nom_jeu} est descendu à {prix:.2f} euros.\n\nLien direct :\n{URL_PRODUIT}"
    url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        reponse = requests.post(url_api, json=payload, timeout=15)
        if reponse.status_code == 200:
            print(f"📱 Message Telegram officiel envoyé avec succès pour {nom_jeu} !")
        else:
            print(f"⚠️ Erreur Telegram : {reponse.text}")
    except Exception as e:
        print(f"⚠️ Erreur lors de l'envoi Telegram : {e}")

def extraire_meilleur_prix():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            locale="fr-FR"
        )
        page = context.new_page()
        try:
            page.goto(URL_PRODUIT, wait_until="commit", timeout=60000)
            page.wait_for_timeout(8000)
            html = page.content()
            texte = page.inner_text("body")
        except Exception as e:
            print(f"⚠️ Temps d'attente dépassé ou erreur : {e}")
            browser.close()
            return None
        browser.close()

    if "MERCHANT" in texte:
        texte = texte.split("MERCHANT", 1)[1]
    for fin in ["Show all offers", "Historical Lowest Prices", "TOP 50"]:
        if fin in texte:
            texte = texte.split(fin, 1)[0]

    prix_trouves = []
    for ligne in texte.split("\n"):
        ligne = ligne.strip()
        if not ligne.startswith("+"):
            m = re.search(r'^(\d+[\.,]\d{2})\s*(?:€|\$|EUR|USD)?$', ligne)
            if m:
                val = float(m.group(1).replace(",", "."))
                if 12.0 <= val <= 150.0:
                    prix_trouves.append(val)

    if not prix_trouves:
        for m in re.finditer(r'(\d{2}[\.,]\d{2})\s*€', html):
            val = float(m.group(1).replace(",", "."))
            if 12.0 <= val <= 150.0:
                prix_trouves.append(val)

    return min(prix_trouves) if prix_trouves else None

def gerer_memoire_et_envoi(prix):
    maintenant = datetime.now(timezone(timedelta(hours=2)))
    heure_actuelle = maintenant.strftime("%Y-%m-%d %H:00")
    heure_minute = maintenant.strftime("%H:%M")

    donnees = {"heure_ref": heure_actuelle, "releves": []}
    if os.path.exists(FICHIER_MEMOIRE):
        try:
            with open(FICHIER_MEMOIRE, "r", encoding="utf-8") as f:
                donnees = json.load(f)
        except Exception:
            pass

    if (donnees["heure_ref"] != heure_actuelle or len(donnees["releves"]) >= 12) and donnees["releves"]:
        donnees["releves"].append({"heure": heure_minute, "prix": prix})
        prix_min = min(r["prix"] for r in donnees["releves"])
        envoyer_email_recap(prix_min, donnees["releves"])
        donnees = {"heure_ref": heure_actuelle, "releves": []}
    else:
        donnees["releves"].append({"heure": heure_minute, "prix": prix})
        print(f"📝 Prix mémorisé ({len(donnees['releves'])}/12 pour l'heure en cours). Prochain mail au changement d'heure.")

    with open(FICHIER_MEMOIRE, "w", encoding="utf-8") as f:
        json.dump(donnees, f)

if __name__ == "__main__":
    prix = extraire_meilleur_prix()
    if prix:
        print(f"✅ Prix MW4 relevé : {prix:.2f} €")
        if prix <= SEUIL_APPEL:
            print(f"🚨 Seuil atteint ({prix:.2f} € <= {SEUIL_APPEL:.2f} €) ! Message Telegram immédiat...")
            envoyer_message_telegram(prix, "Call of Duty Modern Warfare 4")
        gerer_memoire_et_envoi(prix)
    else:
        print("⚠️ Aucun prix détecté sur la page MW4.")
