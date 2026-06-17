# DTE v1.0 — Guide de lancement

## Prérequis

- Python 3.12 installé à `C:\Users\Emma\AppData\Local\Programs\Python\Python312\`
- MetaTrader 5 installé (Deriv)
- Compte demo Deriv : Login `201797413` / Serveur `Deriv-Demo`

---

## Étape 1 — Créer l'environnement virtuel

```powershell
cd c:\thMonster_v2_Top
c:\Users\Emma\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv
```

Si PowerShell bloque les scripts :
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## Étape 2 — Activer le venv

```powershell
.venv\Scripts\Activate.ps1
```

Le prompt affiche `(.venv)` quand c'est actif.

---

## Étape 3 — Installer les dépendances

```powershell
pip install pandas numpy scipy
pip install MetaTrader5
pip install fastapi "uvicorn[standard]" pydantic websockets python-dotenv
pip install anthropic openai
pip install ta colorama
```

> `ta-lib` (avec tiret) est ignoré — difficile à compiler sur Windows et non utilisé par le DTE.
> `tensorflow`, `numba`, `jupyter` etc. sont des restes de l'ancien système, non requis.

---

## Étape 4 — Vérifier MT5 avant le lancement

1. Ouvrir MetaTrader 5
2. **Fichier → Connexion → Compte existant**
   - Login : `201797413`
   - Serveur : `Deriv-Demo`
   - Broker : Deriv.com Limited
   - Mot de passe : `zoldycK*2002`
3. Vérifier que la barre en bas affiche **connecté** (indicateur vert)
4. S'assurer que les 8 symboles Deriv sont visibles dans le Market Watch

---

## Étape 5 — Vérifier la config `.env`

```powershell
Get-Content .env | Select-String "MT5_"
```

Doit afficher :
```
MT5_ACCOUNT_NUMBER=201797413
MT5_PASSWORD=zoldycK*2002
MT5_SERVER=Deriv-Demo
```

---

## Étape 6 — Lancer le bot

```powershell
# Toujours commencer en SIGNAL_ONLY pour valider les signaux
python -m main.dte_main --all-symbols --strategy FLAT --mode SIGNAL_ONLY
```

Sortie attendue dans la **fenêtre principale** :
```
════════════════════════════════════════════════════════════
  DTE v1.0 — SIGNAL_ONLY | 8 symboles | MM:FLAT
  Logs détaillés: fenêtre "DTE — Logs détaillés"
  Résumé positions toutes les 5 minutes
════════════════════════════════════════════════════════════
MT5 connecté | Login:201797413 | Solde:10000.0 USD
```

Puis toutes les 5 minutes :
```
════════════════════════════════════════════════════════════
  18:26:00 | Balance:10000.00$ | Equity:10085.20$ | Session PnL:+85.20$ | Trades:3 | [FULL_AUTO]
  BUY  Crash 500 Index               Vol:0.02 | PnL:+42.10$
  SELL Boom 500 Index                Vol:0.05 | PnL:+31.80$
  BUY  Step Index                    Vol:0.10 | PnL:+11.30$
════════════════════════════════════════════════════════════
```

Et dans la **fenêtre secondaire "DTE — Logs détaillés"** :
```
18:21:27  ──────────────────────── Cycle 0001  [FULL_AUTO]  18:21:27 ────────
18:21:28  ▼*Volatility 100 Index          | Score: 58.5 | SELL | A: 50 B: 50 C: 50 D:71 E:50 | Aln:3
18:21:28  ▲ Crash 500 Index               | Score: 74.7 | BUY  | A:100 B: 50 C: 55 D:62 E:50 | Aln:3
18:21:30  TRADE BUY Crash 500 Index | Vol:0.02 | Prix:3058.0910 | SL:3043.77 TP:3083.62 RR:2.0 ATR:5.9p | Score:74.7
```

---

## Étape 7 — Installer l'extension Chrome (optionnel)

1. Chrome → `chrome://extensions/`
2. Activer **Mode développeur** (haut à droite)
3. Cliquer **"Charger l'extension non empaquetée"**
4. Sélectionner le dossier `c:\thMonster_v2_Top\chrome_extension\`
5. Aller sur `deriv.com` — le panneau DTE apparaît en overlay

---

## Modes disponibles — Commandes

```powershell
# Activer le venv (obligatoire à chaque nouvelle session PowerShell)
cd c:\thMonster_v2_Top
.venv\Scripts\Activate.ps1
```

```powershell
# SIGNAL_ONLY — lecture pure, zéro trade, tous les symboles calculés
python -m main.dte_main --all-symbols --strategy FLAT --mode SIGNAL_ONLY

# SIGNAL_ONLY sans LLM — plus rapide
python -m main.dte_main --all-symbols --strategy FLAT --mode SIGNAL_ONLY --no-llm

# SEMI_AUTO — alerte sur tous les symboles, exécution manuelle
python -m main.dte_main --all-symbols --strategy KELLY --mode SEMI_AUTO

# FULL_AUTO — trade tous les symboles simultanément quand signal valide
python -m main.dte_main --all-symbols --strategy KELLY --mode FULL_AUTO

# FULL_AUTO sans LLM (recommandé en prod — pas de latence API)
python -m main.dte_main --all-symbols --strategy KELLY --mode FULL_AUTO --no-llm

# Symbole unique
python -m main.dte_main --symbol "Crash 500 Index" --strategy KELLY --mode FULL_AUTO
```

> **Note** : en FULL_AUTO `--all-symbols`, le bot peut ouvrir jusqu'à 8 positions simultanées
> (une par symbole). Chaque position est limitée à 2% de risque. Cooldown de 30s par symbole
> après chaque ordre pour éviter les doublons pendant la latence MT5.

---

## Deux fenêtres — Fenêtre principale vs Logs détaillés

À partir du lancement, le bot gère **deux espaces d'affichage** :

| Fenêtre | Contenu | À quelle fréquence |
|---|---|---|
| **Principale** (PS où tu as lancé) | Résumé positions + PnL, chaque TRADE, erreurs critiques | Toutes les 5 min + à chaque trade |
| **Secondaire** (auto-ouverte) titrée "DTE — Logs détaillés" | Tous les signaux cycle par cycle, ATR, trailing/BE | En temps réel, toutes les 2s |

Si tu veux rouvrir manuellement la fenêtre de logs :
```powershell
Get-Content c:\thMonster_v2_Top\logs\dte_20260617.log -Wait -Tail 100
```

---

## Ce qui se passe dans chaque mode

### Boucle commune (tous les modes, toutes les 2 secondes)

Pour **chaque symbole** à chaque cycle :

1. MT5 fournit les bougies M1 (200), M5 (150), M15 (100), H1 (60)
2. Les 5 modèles calculent indépendamment leur score [0–100]
3. La fusion produit un score composite pondéré + une direction (BUY/SELL/WAIT)
4. Si score entre 40 et 65 **et** symbole actif **et** LLM activé → appel Claude Haiku
5. Le signal est loggé en console, poussé à l'API, transmis à l'extension Chrome

Ce pipeline tourne **dans tous les modes**. La différence entre les modes est uniquement ce qui se passe **après** le calcul du signal.

---

### SIGNAL_ONLY — Comment valider les signaux

**Aucun ordre n'est jamais envoyé.** Le bot calcule, affiche, et s'arrête là.

**Ce que tu lis dans la console :**
```
▲ Crash 500 Index    | Score: 82.0 | BUY  | A: 88 B: 75 C: 68 D: 63 E: 72 | Align:3
— Volatility 100     | Score: 51.2 | WAIT | A: 53 B: 50 C: 50 D: 48 E: 52 | Align:1
▼ Boom 500 Index     | Score: 76.4 | SELL | A: 92 B: 75 C: 71 D: 55 E: 69 | Align:3
```

**Comment valider manuellement :**

1. **Ouvre le graphique MT5** du symbole actif en parallèle (Crash 500 en M1)
2. Quand la console affiche `BUY Score:82 Align:3` — observe si le prix monte effectivement dans les minutes suivantes
3. Répète sur 30 à 60 signaux pour avoir une base statistique fiable
4. Critères de validation à surveiller :

| Ce que tu observes | Ce que ça signifie |
|---|---|
| `Align:3` | 3 timeframes pointent dans la même direction — signal plus fiable |
| `Align:1` ou `Align:2` + `reduce_size:true` | Signal faible, souvent suivi d'un WAIT ou d'un mauvais trade |
| Score A > 85 sur Crash/Boom | Streak empirique très fort — validé historiquement à 88-96% |
| Score C > 70 + `spike_alert:HAUTE` | Spike imminent selon la loi exponentielle |
| LLM infirme (`[LLM] Signal annulé`) | Le LLM a jugé le contexte défavorable malgré le score ≥ 40 |
| Score B en compression (≈25) | Marché plat — mauvais timing, le signal A peut être faux |

5. Un signal est **fiable** si : score ≥ 65, Align ≥ 3, Score B > 50 (expansion ou transition), Score A dominant

**Durée recommandée avant de passer en SEMI_AUTO** : 30 à 60 minutes de session, au moins 20 signaux observés avec direction vérifiée sur le graphique.

---

### SEMI_AUTO — Confirmation manuelle

Le calcul est identique à SIGNAL_ONLY. La différence : quand un signal valide est détecté sur le **symbole actif**, le bot affiche explicitement :

```
[SEMI_AUTO] Signal BUY sur Crash 500 Index. Confirmez dans le popup.
```

**Ce mode ne place aucun ordre.** C'est toi qui décides d'entrer ou non, manuellement dans MT5 ou via le popup de l'extension Chrome.

**Processus** :
1. Le bot alerte → tu regardes le graphique MT5
2. Tu juges si le contexte visuel confirme (structure, momentum)
3. Si oui → tu places l'ordre manuellement dans MT5
4. Si non → tu laisses passer

**Ce mode sert à** : prendre confiance dans les signaux en les exécutant toi-même, comparer les résultats manuels avec ce que le FULL_AUTO aurait fait.

---

### FULL_AUTO — Exécution automatique

Quand un signal valide apparaît sur le **symbole actif**, le bot enchaîne automatiquement :

```
Signal BUY Score:82 Align:3
    ↓
compute_sl_tp_dynamic()
  → ATR M1 = 8 pips → SL = max(15, 8×2.5) = 20 pips
  → Score ≥ 80 → RR = 2.5 → TP = 50 pips
    ↓
MoneyManager.get_position_size()
  → Kelly : p=0.82, b=2.5 → f*/4 = 1.8% → montant = 180 USD (sur 10k)
  → score_factor(82) = 0.97 → montant final = 175 USD
    ↓
calculate_volume() → 0.02 lots
    ↓
Vérification : position déjà ouverte sur Crash 500 ? Non → on continue
    ↓
place_order(BUY, 0.02 lots, SL=20p, TP=50p)
    ↓
Log : TRADE BUY Crash 500 | Vol:0.02 | Prix:8547.12 | SL:20.0p TP:50.0p RR:2.5 ATR:8.0p | Score:82
```

**Gardes-fous actifs en FULL_AUTO** :
- Score < 40 → jamais d'ordre (WAIT automatique)
- LLM infirme le signal → WAIT (même si score ≥ 40)
- Position déjà ouverte sur ce symbole → skip
- Drawdown session ≥ 10% → bascule en SIGNAL_ONLY automatiquement
- 1 seul ordre par symbole à la fois

**Seuls les signaux du symbole actif déclenchent des ordres.** Les 7 autres sont calculés et affichés mais jamais tradés.

---

### Changer de mode sans redémarrer

```powershell
# Via l'API (bot en cours d'exécution)
curl -X POST http://localhost:8000/api/mode -H "Content-Type: application/json" -d '{"mode":"FULL_AUTO"}'
curl -X POST http://localhost:8000/api/mode -H "Content-Type: application/json" -d '{"mode":"SIGNAL_ONLY"}'

# Arrêt d'urgence (ferme toutes les positions DTE)
curl -X POST http://localhost:8000/api/emergency_stop
```

Ou directement via les boutons du **popup Chrome** sur deriv.com.

---

### Changer le symbole actif sans redémarrer

```powershell
curl -X POST http://localhost:8000/api/symbol -H "Content-Type: application/json" -d '{"symbol":"Boom 500 Index"}'
```

---

## URLs actives une fois lancé

| Service | URL |
|---|---|
| API REST (racine) | `http://localhost:8000` |
| Status système | `http://localhost:8000/api/status` |
| Signal courant | `http://localhost:8000/api/signal` |
| État complet (extension) | `http://localhost:8000/api/full_state` |
| WebSocket temps réel | `ws://localhost:8000/ws` |

---

## Gestion active des positions — Trailing Stop et Breakeven

En **FULL_AUTO**, le bot surveille les positions ouvertes toutes les **10 secondes** et applique automatiquement :

### Breakeven (mise à zéro du risque)

Dès que le profit d'une position atteint **50% de la distance SL initiale** :
- Le SL est déplacé au prix d'entrée + un léger buffer (2% du SL pour couvrir le spread)
- La position ne peut plus être en perte
- Le TP reste inchangé

```
Exemple : BUY Crash 500 à 3058.0, SL à 3043.8 (14.2 pips de distance)
Breakeven déclenché quand prix ≥ 3058.0 + 7.1 pips = 3065.1
→ SL déplacé à 3058.3 (entry + buffer)
```

### Trailing Stop

Dès que le profit atteint **100% de la distance SL initiale** :
- Le SL suit le prix courant à 50% de la distance SL initiale
- À chaque nouveau prix favorable, le SL monte (BUY) ou descend (SELL)

```
Exemple (suite) : prix monte à 3072.2 (14.2 pips de profit)
→ Trailing activé : SL = 3072.2 - 7.1 = 3065.1
Prix monte encore à 3080.0 :
→ SL mis à jour : 3080.0 - 7.1 = 3072.9
```

Le trailing garantit que si le prix recule, tu sors avec un profit minimum de 50% de la distance SL.

---

## Règles absolues (rappel)

| Règle | Valeur |
|---|---|
| Risque max par trade | 2% du capital |
| Stop session | -10% → bascule en SIGNAL_ONLY automatiquement |
| Score minimum pour trader | 40 / 100 |
| Martingale max | 5 niveaux |
| Magic number MT5 | 20260617 |
